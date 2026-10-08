from typing import Literal

from pydantic import BaseModel, Field


UtteranceRouteType = Literal[
    "noise",
    "response_request",
    "call_to_action",
    "interruption",
]

FloorIntent = Literal[
    "none",
    "backchannel",
    "hold_floor",
    "take_floor",
]


class UtteranceRoute(BaseModel):
    route_type: UtteranceRouteType
    floor_intent: FloorIntent = "none"
    requires_retrieval: bool = False
    proposed_action: str | None = None
    candidate_subjects: list[str] = Field(default_factory=list)
    is_relevant: bool
    should_ignore: bool
    confidence: float
    reason: str
    routing_seconds: float = 0.0
