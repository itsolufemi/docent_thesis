from __future__ import annotations

from collections.abc import Iterator

from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)
from conversation_core.services.cancellation import (
    CancellationToken,
)
from conversation_core.services.control_signal_parser import (
    ControlSignalStreamParser,
)
from conversation_core.services.llm_service import (
    stream_tool_aware_llm_response,
)
from conversation_core.tools.tool_registry import (
    ToolRegistry,
)


def stream_direct_routed_response(
    prompt: str,
    conversation_id: str,
    *,
    buffer_for_tool_decision: bool = False,
    cancellation_token: CancellationToken | None = None,
    max_tool_rounds: int = 5,
    model: str | None = None,
    think: bool | None = None,
    tool_registry: ToolRegistry | None = None,
) -> Iterator[LLMStreamEvent]:
    """Filter exceptional controls out of a tool-aware model stream."""
    parser = ControlSignalStreamParser()

    for event in stream_tool_aware_llm_response(
        prompt=prompt,
        conversation_id=conversation_id,
        buffer_for_tool_decision=buffer_for_tool_decision,
        cancellation_token=cancellation_token,
        max_tool_rounds=max_tool_rounds,
        model=model,
        think=think,
        tool_registry=tool_registry,
    ):
        if event.event_type == "content_delta":
            safe_text = parser.consume(event.text)

            if parser.control_signal is not None:
                yield LLMStreamEvent(
                    event_type="control_signal",
                    control_signal=parser.control_signal,
                )
                return

            if safe_text:
                yield LLMStreamEvent(
                    event_type="content_delta",
                    text=safe_text,
                )

            continue

        if event.event_type == "response_complete":
            safe_text = parser.finish()

            if parser.control_signal is not None:
                yield LLMStreamEvent(
                    event_type="control_signal",
                    control_signal=parser.control_signal,
                )
                return

            if safe_text:
                yield LLMStreamEvent(
                    event_type="content_delta",
                    text=safe_text,
                )

            yield LLMStreamEvent(
                event_type="response_complete",
                text=(
                    event.text
                    if parser.validation_error is None
                    else ""
                ),
                done=True,
            )
            return

        yield event
