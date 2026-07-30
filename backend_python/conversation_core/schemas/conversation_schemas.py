from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


DialogueRole = Literal["user", "assistant", "system"]
ConversationBranchType = Literal["open", "bounded"]
ConversationBranchStatus = Literal[
    "active",
    "closed",
]


class DialogueTurn(BaseModel):
    role: DialogueRole
    content: str


class ConversationSubject(BaseModel):
    """
    A subject being tracked within a conversation branch.

    `label` is the readable form supplied to the LLM.
    `reference` is an optional stable application or domain identifier.
    """

    label: str
    reference: str | None = None


class ConversationBranch(BaseModel):
    """
    A structured representation of the conversational focus
    within one branch of a conversation tree.
    """

    branch_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    name: str
    branch_type: ConversationBranchType

    status: ConversationBranchStatus = "active"

    previous_subjects: list[ConversationSubject] = Field(
        default_factory=list
    )

    current_subjects: list[ConversationSubject] = Field(
        default_factory=list
    )

    remaining_subjects: list[ConversationSubject] = Field(
        default_factory=list
    )


class ConversationTree(BaseModel):
    """
    The structured focus state for one conversation.

    Every branch belongs directly to the conversation, and exactly one
    branch is active at any given time.
    """

    active_branch_id: str

    branches: dict[str, ConversationBranch] = Field(
        default_factory=dict
    )


class ConversationState(BaseModel):
    conversation_id: str

    conversation_tree: ConversationTree

    dialogue_history: list[DialogueTurn] = Field(
        default_factory=list
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class StartConversationResponse(BaseModel):
    conversation_id: str
    state: ConversationState


class SetCurrentSubjectRequest(BaseModel):
    subject_reference: str


class SetCurrentSubjectResponse(BaseModel):
    conversation_id: str
    state: ConversationState
