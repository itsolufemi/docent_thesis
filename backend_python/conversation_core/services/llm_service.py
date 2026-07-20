import httpx
import json

from typing import Any

from config import settings

from conversation_core.schemas.tool_schemas import (
    ToolCall,
    ToolExecutionContext,
)
from conversation_core.tools.core_tool_registry import (
    core_tool_registry,
)

def check_llm_status() -> dict:
    url = f"{settings.ollama_base_url}/api/tags"
    try:
        response =httpx.get(url, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        available_model_names = [
            model.get("name", "")
            for model in models
            if model.get("name")
        ]

        configured_model_available = settings.ollama_model in available_model_names

        if configured_model_available:
            message = 'llm is reachable and the configured model is available'
        else: 
            message = (
                "llm is reachable but the configured model is not available. "
                "Check OLLAMA_MODEL in your .env file."
            )

        return {
            "reachable": True,
            "base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "available_models": available_model_names,
            "message": message
        }
    
    except httpx.ConnectError:
        return {
            "reachable": False,
            "base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "available_models": [],
            "message": "error: couldn't connect the llm"
        }
    
    except Exception as error:
        return {
            "reachable": False,
            "base_url": settings.ollama_base_url,
            "configured_model": settings.ollama_model,
            "available_models": [],
            "message": f"error: {error}"
        }

def generate_llm_response(
    prompt: str,
    model: str | None = None,
    timeout: float = 120.0,
    options: dict[str, Any] | None = None,
) -> str:
    url = f"{settings.ollama_base_url}/api/generate"

    payload = {
        "model": model or settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": options or {},
    }

    try:
        response = httpx.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        return data.get("response", "").strip()
    
    except httpx.ConnectError:
        return "error: couldn't connect the llm"
    
    except httpx.HTTPStatusError as error:
        return f"ollama error: {error.response.status_code} - {error.response.text}"
    
    except Exception as error:
        return f"error: {error}"
    
def build_ollama_tool_definitions() -> list[dict[str, Any]]:
    """
    Convert the application's generic ToolDefinition objects
    into the function-tool format expected by Ollama.
    """

    return [
        {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.parameters,
            },
        }
        for definition in core_tool_registry.get_definitions()
    ]

def parse_ollama_tool_calls(
    response_message: dict[str, Any],
) -> list[ToolCall]:
    """
    Convert Ollama tool-call objects into the application's
    generic ToolCall schema.
    """

    raw_tool_calls = response_message.get("tool_calls") or []

    parsed_tool_calls: list[ToolCall] = []

    for raw_tool_call in raw_tool_calls:
        function_data = raw_tool_call.get("function") or {}

        tool_name = function_data.get("name")
        arguments = function_data.get("arguments") or {}

        if not tool_name:
            continue

        parsed_tool_calls.append(
            ToolCall(
                name=tool_name,
                arguments=arguments,
            )
        )

    return parsed_tool_calls

def send_ollama_chat_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    url = f"{settings.ollama_base_url}/api/chat"

    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
    }

    if tools:
        payload["tools"] = tools

    response = httpx.post(
        url,
        json=payload,
        timeout=120.0,
    )

    response.raise_for_status()

    return response.json()

def generate_tool_aware_llm_response(
    prompt: str,
    conversation_id: str,
    max_tool_rounds: int = 5,
) -> str:
    """
    Ask Ollama for a response while allowing it to call registered tools.

    The loop ends when the model returns an assistant message without
    any tool calls, or when max_tool_rounds is reached.
    """

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    tools = build_ollama_tool_definitions()

    execution_context = ToolExecutionContext(
        conversation_id=conversation_id
    )

    try:
        for _ in range(max_tool_rounds):
            response_data = send_ollama_chat_request(
                messages=messages,
                tools=tools,
            )

            response_message = response_data.get("message") or {}

            messages.append(response_message)

            tool_calls = parse_ollama_tool_calls(
                response_message
            )

            if not tool_calls:
                return (
                    response_message.get("content", "")
                    .strip()
                )

            for tool_call in tool_calls:
                execution_result = core_tool_registry.execute(
                    tool_call=tool_call,
                    context=execution_context,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_call.name,
                        "content": execution_result.model_dump_json(),
                    }
                )

        return (
            "I could not complete the operation because the "
            "tool-calling limit was reached."
        )

    except httpx.ConnectError:
        return "error: couldn't connect the llm"

    except httpx.HTTPStatusError as error:
        return (
            f"ollama error: {error.response.status_code} - "
            f"{error.response.text}"
        )

    except Exception as error:
        return f"error: {error}"
    
