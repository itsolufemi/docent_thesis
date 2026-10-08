from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class SelfRoutingAssessment(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    route_type: Literal[
        "response_request",
        "call_to_action",
        "interruption",
        "noise",
    ]

    is_relevant: bool

    candidate_subjects: list[str] = Field(
        default_factory=list
    )

    should_update_subject: bool = False

    proposed_action: str | None = None

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    reason: str