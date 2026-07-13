from pydantic import BaseModel, Field

from conversation_core.schemas.conversation_schemas import (
    ConversationBranchType,
)


class ToolSubjectInput(BaseModel):
    label: str
    reference: str | None = None


class CreateConversationBranchArguments(BaseModel):
    name: str
    branch_type: ConversationBranchType

    current_subjects: list[ToolSubjectInput] = Field(
        default_factory=list
    )

    remaining_subjects: list[ToolSubjectInput] = Field(
        default_factory=list
    )


class UpdateActiveBranchArguments(BaseModel):
    previous_subjects: list[ToolSubjectInput] | None = None
    current_subjects: list[ToolSubjectInput] | None = None
    remaining_subjects: list[ToolSubjectInput] | None = None


class CloseActiveBranchArguments(BaseModel):
    reason: str | None = None