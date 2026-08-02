from typing import Any, Literal

from pydantic import BaseModel, Field


LLMStreamEventType = Literal[
    "response_started",
    "self_routing",
    "content_delta",
    "tool_call",
    "tool_result",
    "timing",
    "response_complete",
    "response_cancelled",
]


class LLMStreamEvent(BaseModel):
    event_type: LLMStreamEventType
    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list
    )
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None
    route_assessment: dict[str, Any] | None = None
    timing_name: str | None = None
    timing_seconds: float | None = Field(
        default=None,
        ge=0,
    )
    timing_payload: dict[str, Any] = Field(
        default_factory=dict
    )
    done: bool = False
