from collections.abc import Iterator
from typing import Any

from conversation_core.schemas.llm_stream_schemas import LLMStreamEvent
from conversation_core.services.cancellation import CancellationToken
from conversation_core.services.llm_service import stream_ollama_chat_request


def stream_llm_response(
    prompt: str,
    *,
    cancellation_token: CancellationToken | None = None,
    model: str | None = None,
    think: bool | None = None,
) -> Iterator[LLMStreamEvent]:
    """Stream one tool-free Ollama response."""
    if (
        cancellation_token is not None
        and cancellation_token.is_cancelled
    ):
        yield LLMStreamEvent(
            event_type="response_cancelled",
            done=True,
        )
        return

    pending_timings: list[
        tuple[str, float, dict[str, Any]]
    ] = []

    def capture_timing(
        name: str,
        seconds: float,
        payload: dict[str, Any],
    ) -> None:
        pending_timings.append(
            (name, seconds, payload)
        )

    yield LLMStreamEvent(
        event_type="response_started"
    )

    response_parts: list[str] = []

    for chunk in stream_ollama_chat_request(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        tools=None,
        cancellation_token=cancellation_token,
        model=model,
        think=think,
        timing_callback=capture_timing,
        round_number=1,
    ):
        while pending_timings:
            name, seconds, payload = pending_timings.pop(0)
            yield LLMStreamEvent(
                event_type="timing",
                timing_name=name,
                timing_seconds=round(seconds, 4),
                timing_payload=payload,
            )

        if (
            cancellation_token is not None
            and cancellation_token.is_cancelled
        ):
            yield LLMStreamEvent(
                event_type="response_cancelled",
                done=True,
            )
            return

        message = chunk.get("message") or {}
        content = message.get("content") or ""

        if content:
            response_parts.append(content)
            yield LLMStreamEvent(
                event_type="content_delta",
                text=content,
            )

    while pending_timings:
        name, seconds, payload = pending_timings.pop(0)
        yield LLMStreamEvent(
            event_type="timing",
            timing_name=name,
            timing_seconds=round(seconds, 4),
            timing_payload=payload,
        )

    yield LLMStreamEvent(
        event_type="response_complete",
        text="".join(response_parts).strip(),
        done=True,
    )
