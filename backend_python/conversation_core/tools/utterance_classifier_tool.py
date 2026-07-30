from typing import Literal

from pydantic import BaseModel, Field

from conversation_core.schemas.tool_schemas import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)
from conversation_core.services.utterance_router_service import (
    normalise_route_payload,
)
from conversation_core.tools.tool_registry import (
    ToolRegistry,
)
from docent.config.docent_classifier_profile import (
    docent_classifier_profile,
)


CLASSIFY_UTTERANCE_TOOL_NAME = (
    "classify_utterance"
)


class ClassifyUtteranceArguments(BaseModel):
    utterance: str = Field(min_length=1)
    route_type: Literal[
        "noise",
        "response_request",
        "call_to_action",
        "interruption",
    ]
    floor_intent: Literal[
        "none",
        "backchannel",
        "hold_floor",
        "take_floor",
    ]
    requires_retrieval: bool
    proposed_action: Literal[
        "create_bounded_branch",
        "close_bounded_branch",
        "none",
    ] | None = None
    candidate_subjects: list[str] = Field(
        default_factory=list
    )


def handle_classify_utterance(
    context: ToolExecutionContext,
    raw_arguments: dict,
) -> ToolExecutionResult:
    arguments = (
        ClassifyUtteranceArguments
        .model_validate(raw_arguments)
    )
    utterance = arguments.utterance.strip()

    if not utterance:
        return ToolExecutionResult(
            tool_name=(
                CLASSIFY_UTTERANCE_TOOL_NAME
            ),
            success=False,
            message=(
                "The utterance cannot be empty."
            ),
        )

    route = normalise_route_payload(
        payload={
            "route_type": (
                arguments.route_type
            ),
            "floor_intent": (
                arguments.floor_intent
            ),
            "requires_retrieval": (
                arguments
                .requires_retrieval
            ),
            "proposed_action": (
                None
                if arguments.proposed_action
                in {None, "none"}
                else arguments.proposed_action
            ),
            "candidate_subjects": (
                arguments
                .candidate_subjects
            ),
            "is_relevant": (
                arguments.route_type
                != "noise"
            ),
            "should_ignore": (
                arguments.route_type
                == "noise"
            ),
            "confidence": 0.5,
            "reason": (
                "Classification supplied by the "
                "main model through the mandatory "
                "tool call."
            ),
        },
        domain_profile=(
            docent_classifier_profile
        ),
    )

    return ToolExecutionResult(
        tool_name=(
            CLASSIFY_UTTERANCE_TOOL_NAME
        ),
        success=True,
        message=(
            "The latest user utterance was "
            "classified successfully."
        ),
        data={
            "utterance_route": route.model_dump(
                mode="json"
            ),
        },
    )


CLASSIFY_UTTERANCE_DEFINITION = (
    ToolDefinition(
        name=CLASSIFY_UTTERANCE_TOOL_NAME,
        description=(
            "Submit your structured classification "
            "of the user's latest utterance before "
            "answering. This tool must be called "
            "exactly once for every new user "
            "utterance. Its arguments are the "
            "classification result; the backend "
            "does not call another classifier."
        ),
        parameters={
            "type": "object",
            "properties": {
                "utterance": {
                    "type": "string",
                    "description": (
                        "The user's complete latest "
                        "utterance, copied unchanged."
                    ),
                },
                "route_type": {
                    "type": "string",
                    "enum": [
                        "noise",
                        "response_request",
                        "call_to_action",
                        "interruption",
                    ],
                },
                "floor_intent": {
                    "type": "string",
                    "enum": [
                        "none",
                        "backchannel",
                        "hold_floor",
                        "take_floor",
                    ],
                },
                "requires_retrieval": {
                    "type": "boolean",
                },
                "proposed_action": {
                    "type": "string",
                    "enum": [
                        "none",
                        "create_bounded_branch",
                        "close_bounded_branch",
                    ],
                    "description": (
                        "Use 'none' unless the utterance "
                        "explicitly requests one of the "
                        "available actions."
                    ),
                },
                "candidate_subjects": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
            "required": [
                "utterance",
                "route_type",
                "floor_intent",
                "requires_retrieval",
                "proposed_action",
                "candidate_subjects",
            ],
            "additionalProperties": False,
        },
    )
)


def register_utterance_classifier_tool(
    registry: ToolRegistry,
) -> None:
    registry.register(
        definition=(
            CLASSIFY_UTTERANCE_DEFINITION
        ),
        handler=handle_classify_utterance,
    )
