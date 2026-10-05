import httpx
import json
import re

from collections.abc import Callable, Iterator
from enum import Enum
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
from conversation_core.tools.tool_registry import (
    ToolRegistry,
)

LLMTimingCallback = Callable[
    [str, float, dict[str, Any]],
    None,
]

POST_ANSWER_PROBE_INSTRUCTION = (
    "The visitor's primary answer has already been delivered. Do not repeat "
    "or continue that answer yet. Decide whether one worthwhile optional "
    "post-answer tool action would naturally extend it. If so, call an "
    "available post-answer tool. Otherwise produce no text and finish."
)

POST_DISCOVERY_CONTINUATION_INSTRUCTION = (
    "The primary answer has already been delivered. Use the post-answer tool "
    "result only if it adds something worthwhile. Add at most one short natural "
    "continuation. Do not repeat the primary answer. If no worthwhile "
    "continuation exists, return an empty response. Never say 'No additional "
    "text', 'Nothing to add', or describe this decision. Do not emit control "
    "tags, routing metadata, tool calls, or diagnostic text. Return only the "
    "optional visitor-facing continuation, or an empty response."
)

EMPTY_CONTINUATION_RESPONSES = {
    "no additional text",
    "no additional text.",
}

CONTROL_BLOCK_PATTERN = re.compile(
    r"<control>.*?</control>\s*",
    flags=re.DOTALL,
)

DUPLICATE_TOOL_CALL_INSTRUCTION = (
    "The requested tool call has already been executed with the same "
    "arguments during this response phase. Do not call it again. Use the "
    "evidence already available and continue the response."
)


class ToolResponsePhase(str, Enum):
    PRIMARY = "primary"
    POST_ANSWER_PROBE = "post_answer"
    CONTINUATION = "continuation"


def tool_call_signature(tool_call: ToolCall) -> str:
    arguments_json = json.dumps(
        tool_call.arguments,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"{tool_call.name}:{arguments_json}"


def _contains_complete_sentence(text: str) -> bool:
    return bool(
        re.search(r'[.!?](?:["\')\]]*)?(?:\s|$)', text)
    )

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
    
def build_ollama_tool_definitions(
    tool_registry: ToolRegistry | None = None,
) -> list[dict[str, Any]]:
    """
    Convert the application's generic ToolDefinition objects
    into the function-tool format expected by Ollama.
    """

    registry = tool_registry or core_tool_registry

    return [
        {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.parameters,
            },
        }
        for definition in registry.get_definitions()
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
    tool_registry: ToolRegistry | None = None,
) -> Iterator[LLMStreamEvent]:
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": prompt,
        }
    ]
    active_tool_registry = tool_registry or core_tool_registry
    definitions = active_tool_registry.get_definitions()
    tool_definitions = build_ollama_tool_definitions(
        active_tool_registry
    )
    primary_tool_names = {
        definition.name
        for definition in definitions
        if "primary" in definition.allowed_phases
    }
    post_answer_tool_names = {
        definition.name
        for definition in definitions
        if "post_answer" in definition.allowed_phases
    }
    primary_tools = [
        tool
        for tool in tool_definitions
        if tool.get("function", {}).get("name") in primary_tool_names
    ]
    post_answer_tools = [
        tool
        for tool in tool_definitions
        if tool.get("function", {}).get("name") in post_answer_tool_names
    ]

    def tools_for_phase(
        response_phase: ToolResponsePhase,
    ) -> list[dict[str, Any]] | None:
        if response_phase == ToolResponsePhase.PRIMARY:
            return primary_tools
        if response_phase == ToolResponsePhase.POST_ANSWER_PROBE:
            return post_answer_tools
        return None

    execution_context = ToolExecutionContext(
        conversation_id=conversation_id
    )
    phase = ToolResponsePhase.PRIMARY
    visitor_text_emitted = False
    executed_call_signatures: dict[
        ToolResponsePhase,
        set[str],
    ] = {
        response_phase: set()
        for response_phase in ToolResponsePhase
    }
    duplicate_recovery_attempted: dict[
        ToolResponsePhase,
        bool,
    ] = {
        response_phase: False
        for response_phase in ToolResponsePhase
    }

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
                phase != ToolResponsePhase.PRIMARY
                or (
                    buffer_for_tool_decision
                    and not execution_context.executed_tool_names
                )
            )
            round_tools = tools_for_phase(phase)
            allowed_round_tool_names = {
                tool.get("function", {}).get("name")
                for tool in (round_tools or [])
            }

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
                tools=round_tools,
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
                        visitor_text_emitted = True
                        if (
                            not execution_context.visitor_sentence_emitted
                            and _contains_complete_sentence(
                                "".join(round_content_parts)
                            )
                        ):
                            execution_context.visitor_sentence_emitted = True

                if raw_tool_calls:
                    round_tool_calls.extend(
                        tool_call
                        for tool_call in parse_ollama_tool_calls(
                            response_message
                        )
                        if tool_call.name in allowed_round_tool_names
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

            if phase == ToolResponsePhase.CONTINUATION:
                complete_round_content = (
                    CONTROL_BLOCK_PATTERN.sub(
                        "",
                        complete_round_content,
                    ).strip()
                )

            if (
                phase == ToolResponsePhase.CONTINUATION
                and complete_round_content.casefold()
                in EMPTY_CONTINUATION_RESPONSES
            ):
                complete_round_content = ""

            if (
                phase == ToolResponsePhase.CONTINUATION
                and visitor_text_emitted
                and complete_round_content
            ):
                complete_round_content = (
                    f" {complete_round_content}"
                )

            accepted_tool_calls: list[
                tuple[ToolCall, str]
            ] = []
            duplicate_tool_calls: list[
                tuple[ToolCall, str]
            ] = []
            for tool_call in round_tool_calls:
                signature = tool_call_signature(tool_call)
                if (
                    signature
                    in executed_call_signatures[phase]
                ):
                    duplicate_tool_calls.append(
                        (tool_call, signature)
                    )
                else:
                    accepted_tool_calls.append(
                        (tool_call, signature)
                    )

            for tool_call, signature in duplicate_tool_calls:
                yield LLMStreamEvent(
                    event_type="tool_call_suppressed",
                    tool_name=tool_call.name,
                    tool_calls=[
                        tool_call.model_dump(mode="json")
                    ],
                    tool_telemetry={
                        "tool_name": tool_call.name,
                        "response_phase": phase.value,
                        "call_signature": signature,
                        "duplicate": True,
                        "reason": "duplicate_call_same_phase",
                    },
                )

            if accepted_tool_calls:
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
                            for tool_call, _signature
                            in accepted_tool_calls
                        ],
                    }
                )

                post_answer_tool_succeeded = False
                for tool_call, signature in accepted_tool_calls:
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
                        tool_telemetry={
                            "tool_name": tool_call.name,
                            "response_phase": phase.value,
                            "call_signature": signature,
                            "duplicate": False,
                            "purpose": tool_call.arguments.get(
                                "purpose"
                            ),
                        },
                    )

                    executed_call_signatures[phase].add(
                        signature
                    )
                    execution_context.response_phase = (
                        phase.value
                    )
                    execution_result = (
                        active_tool_registry.execute(
                            tool_call=tool_call,
                            context=execution_context,
                        )
                    )
                    execution_context.executed_tool_names.append(
                        tool_call.name
                    )
                    if (
                        phase
                        == ToolResponsePhase.POST_ANSWER_PROBE
                        and execution_result.success
                    ):
                        post_answer_tool_succeeded = True

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
                                json.dumps(
                                    execution_result.model_payload(),
                                    ensure_ascii=False,
                                )
                            ),
                        }
                    )

                    yield LLMStreamEvent(
                        event_type="tool_result",
                        tool_name=tool_call.name,
                        tool_result=result_payload,
                        tool_telemetry={
                            "tool_name": tool_call.name,
                            "response_phase": phase.value,
                            "call_signature": signature,
                            "duplicate": False,
                            "purpose": tool_call.arguments.get(
                                "purpose"
                            ),
                        },
                    )

                if post_answer_tool_succeeded:
                    phase = ToolResponsePhase.CONTINUATION
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                POST_DISCOVERY_CONTINUATION_INSTRUCTION
                            ),
                        }
                    )
                continue

            if round_tool_calls and not accepted_tool_calls:
                if duplicate_recovery_attempted[phase]:
                    if visitor_text_emitted:
                        yield LLMStreamEvent(
                            event_type="response_complete",
                            text="",
                            done=True,
                        )
                    else:
                        recovery_failure = (
                            "I'm sorry, I couldn't complete that response."
                        )
                        yield LLMStreamEvent(
                            event_type="content_delta",
                            text=recovery_failure,
                        )
                        yield LLMStreamEvent(
                            event_type="response_complete",
                            text=recovery_failure,
                            done=True,
                        )
                    return

                duplicate_recovery_attempted[phase] = True
                messages.append(
                    {
                        "role": "system",
                        "content": DUPLICATE_TOOL_CALL_INSTRUCTION,
                    }
                )
                continue

            if phase == ToolResponsePhase.PRIMARY:
                if complete_round_content and buffer_current_round:
                    yield LLMStreamEvent(
                        event_type="content_delta",
                        text=complete_round_content,
                    )
                    visitor_text_emitted = True
                    if (
                        not execution_context.visitor_sentence_emitted
                        and _contains_complete_sentence(
                            complete_round_content
                        )
                    ):
                        execution_context.visitor_sentence_emitted = True

                if complete_round_content and post_answer_tools:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": complete_round_content,
                        }
                    )
                    messages.append(
                        {
                            "role": "system",
                            "content": POST_ANSWER_PROBE_INSTRUCTION,
                        }
                    )
                    phase = ToolResponsePhase.POST_ANSWER_PROBE
                    continue

                yield LLMStreamEvent(
                    event_type="response_complete",
                    text=complete_round_content,
                    done=True,
                )
                return

            if phase == ToolResponsePhase.POST_ANSWER_PROBE:
                yield LLMStreamEvent(
                    event_type="response_complete",
                    text="",
                    done=True,
                )
                return

            if complete_round_content:
                yield LLMStreamEvent(
                    event_type="content_delta",
                    text=complete_round_content,
                )
                visitor_text_emitted = True

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
    
