from typing import Literal

from pydantic import BaseModel, Field


class ModelRouteAssessment(BaseModel):
    route_type: Literal[
        "response_request",
        "call_to_action",
        "interruption",
        "noise",
    ]
    is_relevant: bool
    should_ignore: bool
    retrieval_required: bool
    retrieved_context_used: bool
    proposed_action: str | None = None
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    reason: str
