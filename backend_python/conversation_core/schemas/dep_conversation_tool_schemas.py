"""
DEPRECATED REFERENCE IMPLEMENTATION.

This module belongs to the retired conversation-tree architecture.
It is intentionally disconnected from the active application and may
not import successfully because its former state models and store
operations have been removed.

Restore the associated schemas and conversation-store functions before
attempting to reactivate this implementation.
"""

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


class CloseActiveBranchArguments(BaseModel):
    reason: str | None = None
