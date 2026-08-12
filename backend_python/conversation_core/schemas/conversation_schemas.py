from pydantic import BaseModel, Field


class DialogueTurn(BaseModel):
    previous_subject: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)
    reference: list[str] = Field(default_factory=list)
    user: str | None = None
    assistant: str | None = None


class ConversationState(BaseModel):
    conversation_id: str
    dialogue_history: list[DialogueTurn] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    metadata: dict[str, object] = Field(
        default_factory=dict
    )


class StartConversationResponse(BaseModel):
    conversation_id: str
    state: ConversationState
