import httpx
import json

from collections.abc import Callable, Iterator
from time import perf_counter
from typing import Any

from config import settings

from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)
from conversation_core.services.cancellation import (
    CancellationToken,
)
from conversation_core.services.ollama_http_client import (
    ollama_http_client,
)
from conversation_core.schemas.tool_schemas import (
    ToolCall,
    ToolExecutionContext,
)
from conversation_core.tools.core_tool_registry import (
    core_tool_registry,
)

LLMTimingCallback = Callable[
    [str, float, dict[str, Any]],
    None,
]

def check_llm_status() -> dict:
    try:
        response = ollama_http_client.get(
            "/api/tags",
            timeout=10.0,
        )
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
    think: bool | None = None,
) -> str:
    payload = {
        "model": model or settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": options or {},
    }

    if think is not None:
        payload["think"] = think

    try:
        response = ollama_http_client.post(
            "/api/generate",
            json=payload,
            timeout=timeout,
        )
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
    *,
    model: str | None = None,
    think: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model or settings.ollama_model,
        "messages": messages,
        "stream": False,
    }

    if tools:
        payload["tools"] = tools

    selected_think = (
        settings.ollama_main_think
        if think is None
        else think
    )

    if selected_think is not None:
        payload["think"] = selected_think

    response = ollama_http_client.post(
        "/api/chat",
        json=payload,
        timeout=120.0,
    )

    response.raise_for_status()

    return response.json()


def stream_ollama_chat_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    cancellation_token: CancellationToken | None = None,
    *,
    model: str | None = None,
    think: bool | None = None,
    timing_callback: LLMTimingCallback | None = None,
    round_number: int = 1,
) -> Iterator[dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": model or settings.ollama_model,
        "messages": messages,
        "stream": True,
    }

    if tools:
        payload["tools"] = tools

    selected_think = (
        settings.ollama_main_think
        if think is None
        else think
    )

    if selected_think is not None:
        payload["think"] = selected_think

    if (
        cancellation_token is not None
        and cancellation_token.is_cancelled
    ):
        return

    request_started_at = perf_counter()

    with ollama_http_client.stream(
        method="POST",
        url="/api/chat",
        json=payload,
        timeout=120.0,
    ) as response:
        response.raise_for_status()

        if timing_callback is not None:
            timing_callback(
                "ollama_response_headers_seconds",
                perf_counter() - request_started_at,
                {"round": round_number},
            )

        first_parsed_chunk_received = False

        for line in response.iter_lines():
            if (
                cancellation_token is not None
                and cancellation_token.is_cancelled
            ):
                response.close()
                return

            if not line:
                continue

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not first_parsed_chunk_received:
                first_parsed_chunk_received = True

                if timing_callback is not None:
                    timing_callback(
                        "ollama_first_chunk_seconds",
                        perf_counter() - request_started_at,
                        {"round": round_number},
                    )

            yield chunk


def warm_up_main_llm() -> dict:
    started_at = perf_counter()
    response_data = send_ollama_chat_request(
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: ready",
            }
        ],
        tools=None,
        think=False,
    )
    content = (
        response_data.get("message", {})
        .get("content", "")
        .strip()
    )

    if not content:
        raise RuntimeError(
            "The LLM warm-up returned no content."
        )

    return {
        "seconds": round(
            perf_counter() - started_at,
            4,
        ),
        "response": content[:50],
    }


def stream_tool_aware_llm_response(
    prompt: str,
    conversation_id: str,
    *,
    buffer_for_tool_decision: bool,
    cancellation_token: CancellationToken | None = None,
    max_tool_rounds: int = 5,
    model: str | None = None,
    think: bool | None = None,
) -> Iterator[LLMStreamEvent]:
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
    tool_has_executed = False

    if (
        cancellation_token is not None
        and cancellation_token.is_cancelled
    ):
        yield LLMStreamEvent(
            event_type="response_cancelled",
            done=True,
        )
        return

    yield LLMStreamEvent(
        event_type="response_started",
    )

    try:
        for round_index in range(max_tool_rounds):
            round_number = round_index + 1
            if (
                cancellation_token is not None
                and cancellation_token.is_cancelled
            ):
                yield LLMStreamEvent(
                    event_type="response_cancelled",
                    done=True,
                )
                return

            round_content_parts: list[str] = []
            round_tool_calls: list[ToolCall] = []
            buffer_current_round = (
                buffer_for_tool_decision
                and not tool_has_executed
            )

            pending_timing_events: list[
                LLMStreamEvent
            ] = []
            first_content_chunk_received = False
            round_started_at = perf_counter()

            def record_llm_timing(
                timing_name: str,
                timing_seconds: float,
                timing_payload: dict[str, Any],
            ) -> None:
                pending_timing_events.append(
                    LLMStreamEvent(
                        event_type="timing",
                        timing_name=timing_name,
                        timing_seconds=round(
                            timing_seconds,
                            4,
                        ),
                        timing_payload=timing_payload,
                    )
                )

            for chunk in stream_ollama_chat_request(
                messages=messages,
                tools=tools,
                cancellation_token=(
                    cancellation_token
                ),
                model=model,
                think=think,
                timing_callback=record_llm_timing,
                round_number=round_number,
            ):
                while pending_timing_events:
                    yield pending_timing_events.pop(0)

                response_message = (
                    chunk.get("message") or {}
                )
                content_delta = (
                    response_message.get("content")
                    or ""
                )

                if (
                    content_delta
                    and not first_content_chunk_received
                ):
                    first_content_chunk_received = True
                    yield LLMStreamEvent(
                        event_type="timing",
                        timing_name=(
                            "ollama_first_content_chunk_seconds"
                        ),
                        timing_seconds=round(
                            perf_counter() - round_started_at,
                            4,
                        ),
                        timing_payload={
                            "round": round_number,
                        },
                    )
                raw_tool_calls = (
                    response_message.get(
                        "tool_calls"
                    )
                    or []
                )

                if content_delta:
                    round_content_parts.append(
                        content_delta
                    )

                    if not buffer_current_round:
                        yield LLMStreamEvent(
                            event_type="content_delta",
                            text=content_delta,
                        )

                if raw_tool_calls:
                    round_tool_calls.extend(
                        parse_ollama_tool_calls(
                            response_message
                        )
                    )

                if chunk.get("done"):
                    break

            while pending_timing_events:
                yield pending_timing_events.pop(0)

            if (
                cancellation_token is not None
                and cancellation_token.is_cancelled
            ):
                yield LLMStreamEvent(
                    event_type="response_cancelled",
                    done=True,
                )
                return

            complete_round_content = "".join(
                round_content_parts
            ).strip()

            if round_tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": (
                            complete_round_content
                        ),
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": (
                                        tool_call.name
                                    ),
                                    "arguments": (
                                        tool_call.arguments
                                    ),
                                },
                            }
                            for tool_call
                            in round_tool_calls
                        ],
                    }
                )

                for tool_call in round_tool_calls:
                    if (
                        cancellation_token is not None
                        and cancellation_token.is_cancelled
                    ):
                        yield LLMStreamEvent(
                            event_type=(
                                "response_cancelled"
                            ),
                            done=True,
                        )
                        return

                    yield LLMStreamEvent(
                        event_type="tool_call",
                        tool_calls=[
                            tool_call.model_dump(
                                mode="json"
                            )
                        ],
                    )

                    execution_result = (
                        core_tool_registry.execute(
                            tool_call=tool_call,
                            context=execution_context,
                        )
                    )

                    if (
                        cancellation_token is not None
                        and cancellation_token.is_cancelled
                    ):
                        yield LLMStreamEvent(
                            event_type=(
                                "response_cancelled"
                            ),
                            done=True,
                        )
                        return

                    result_payload = (
                        execution_result.model_dump(
                            mode="json"
                        )
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_name": (
                                tool_call.name
                            ),
                            "content": (
                                execution_result
                                .model_dump_json()
                            ),
                        }
                    )

                    yield LLMStreamEvent(
                        event_type="tool_result",
                        tool_name=tool_call.name,
                        tool_result=result_payload,
                    )

                tool_has_executed = True
                continue

            if (
                complete_round_content
                and buffer_current_round
            ):
                yield LLMStreamEvent(
                    event_type="content_delta",
                    text=complete_round_content,
                )

            yield LLMStreamEvent(
                event_type="response_complete",
                text=complete_round_content,
                done=True,
            )
            return

        if (
            cancellation_token is not None
            and cancellation_token.is_cancelled
        ):
            yield LLMStreamEvent(
                event_type="response_cancelled",
                done=True,
            )
            return

        limit_message = (
            "I could not complete the operation "
            "because the tool-calling limit "
            "was reached."
        )

        yield LLMStreamEvent(
            event_type="content_delta",
            text=limit_message,
        )
        yield LLMStreamEvent(
            event_type="response_complete",
            text=limit_message,
            done=True,
        )
    except httpx.ConnectError:
        error_message = "error: couldn't connect the llm"
    except httpx.HTTPStatusError as error:
        error_message = (
            f"ollama error: {error.response.status_code} - "
            f"{error.response.text}"
        )
    except Exception as error:
        error_message = f"error: {error}"
    else:
        return

    if (
        cancellation_token is not None
        and cancellation_token.is_cancelled
    ):
        yield LLMStreamEvent(
            event_type="response_cancelled",
            done=True,
        )
        return

    yield LLMStreamEvent(
        event_type="content_delta",
        text=error_message,
    )
    yield LLMStreamEvent(
        event_type="response_complete",
        text=error_message,
        done=True,
    )


def generate_tool_aware_llm_response(
    prompt: str,
    conversation_id: str,
    max_tool_rounds: int = 5,
    *,
    model: str | None = None,
    think: bool | None = None,
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
                model=model,
                think=think,
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
    
