from typing import Any, Literal

from pydantic import BaseModel, Field


LLMStreamEventType = Literal[
    "response_started",
    "content_delta",
    "tool_call",
    "tool_result",
    "response_complete",
]


class LLMStreamEvent(BaseModel):
    event_type: LLMStreamEventType
    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list
    )
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None
    done: bool = False
