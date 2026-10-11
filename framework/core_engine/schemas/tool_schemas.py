from typing import Any, Literal

from pydantic import BaseModel, Field

from core_engine.schemas.source_schemas import (
    QuerySource,
)
from core_engine.schemas.multimodal_schemas import ImageInput


ToolPhase = Literal[
    "primary",
    "post_answer",
]

ToolExecutionPhase = Literal[
    "primary",
    "post_answer",
    "continuation",
]


class ToolDefinition(BaseModel):
    """
    Describes a tool that may be presented to an LLM.

    The parameters field contains a JSON Schema describing
    the arguments the model is allowed to provide.
    """

    name: str
    description: str

    parameters: dict[str, Any] = Field(
        default_factory=dict
    )
    allowed_phases: set[ToolPhase] = Field(
        default_factory=lambda: {"primary"}
    )


class ToolCall(BaseModel):
    """
    A structured request from the LLM to execute one tool.
    """

    name: str

    arguments: dict[str, Any] = Field(
        default_factory=dict
    )


class ToolExecutionContext(BaseModel):
    """
    Trusted application context supplied by the server.

    These values are not chosen by the LLM.
    """

    conversation_id: str
    visitor_sentence_emitted: bool = False
    response_phase: ToolExecutionPhase = "primary"
    executed_tool_names: list[str] = Field(
        default_factory=list
    )


class ToolDialogueStateUpdate(BaseModel):
    """Domain-neutral dialogue state discovered by a tool."""

    subjects: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class ToolExecutionResult(BaseModel):
    """
    The normalized result returned after executing a tool.
    """

    tool_name: str
    success: bool

    message: str

    data: dict[str, Any] = Field(
        default_factory=dict
    )

    retrieval_used: bool = False

    dialogue_state: ToolDialogueStateUpdate | None = None

    sources: list[QuerySource] = Field(
        default_factory=list
    )

    telemetry: dict[str, Any] = Field(
        default_factory=dict
    )

    # In-memory attachments for the next model request. Excluded from all
    # model_dump/model_dump_json output, telemetry, and public tool results.
    image_attachments: list[ImageInput] = Field(
        default_factory=list,
        exclude=True,
        repr=False,
    )

    def model_payload(self) -> dict[str, Any]:
        """Return only the data needed by the model's next round."""
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
        }
