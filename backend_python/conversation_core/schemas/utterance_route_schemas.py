from typing import Literal

from pydantic import BaseModel, Field


UtteranceRouteType = Literal[
    "noise",
    "response_request",
    "call_to_action",
    "interruption",
]


class UtteranceRoute(BaseModel):
    route_type: UtteranceRouteType
    requires_retrieval: bool = False
    proposed_action: str | None = None
    candidate_subjects: list[str] = Field(default_factory=list)
    is_relevant: bool
    should_ignore: bool
    confidence: float
    reason: str
    routing_seconds: float = 0.0
