from typing import Literal

from pydantic import BaseModel, Field


DialogueRole = Literal[
    "user",
    "assistant",
    "system",
]


class DialogueTurn(BaseModel):
    role: DialogueRole
    content: str

    subjects: list[str] = Field(
        default_factory=list
    )

    # Legacy singular fields remain temporarily for compatibility with
    # inactive query paths. The active context-resolution pipeline writes
    # only `subjects`.
    previous_subject: str | None = None
    current_subject: str | None = None
    current_subject_reference: str | None = None


class ConversationState(BaseModel):
    conversation_id: str

    dialogue_history: list[DialogueTurn] = Field(
        default_factory=list
    )

    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class StartConversationResponse(BaseModel):
    conversation_id: str
    state: ConversationState
