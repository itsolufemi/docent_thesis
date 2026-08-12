from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContextResolutionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_relevant: bool
    route_type: Literal[
        "response_request",
        "call_to_action",
        "interruption",
        "backchannel",
        "noise",
    ]
    requires_retrieval: bool
    subjects: list[str] = Field(default_factory=list)
