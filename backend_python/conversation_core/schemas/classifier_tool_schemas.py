from typing import Any

from pydantic import BaseModel, Field

from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)


class ClassifierToolAudit(BaseModel):
    classifier_call_count: int
    classifier_called_exactly_once: bool
    classifier_omitted: bool
    classifier_called_more_than_once: bool
    invalid_classifier_arguments: bool
    model_returned_content: bool
    model_to_tool_call_seconds: float
    classifier_execution_seconds: float
    total_seconds: float


class ClassifierToolRoundResult(BaseModel):
    utterance: str
    utterance_route: UtteranceRoute
    audit: ClassifierToolAudit
    prompt: str
    continuation_messages: list[
        dict[str, Any]
    ] = Field(
        default_factory=list,
        exclude=True,
    )
