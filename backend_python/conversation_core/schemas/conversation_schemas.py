from typing import Literal
from pydantic import BaseModel, Field

dialogueRole = Literal["user", "assistant", "system"]

class DialogueTurn(BaseModel):
    role: dialogueRole
    content: str

class ConversationState(BaseModel):
    conversation_id: str
    current_subject: str | None = None
    previous_subject: str | None = None
    discussed_subjects: list[str] = Field(default_factory=list)
    dialogue_history: list[DialogueTurn] = Field(default_factory=list)


class StartConversationResponse(BaseModel):
    conversation_id: str
    state: ConversationState

class SetCurrentSubjectRequest(BaseModel):
    subject: str

class SetCurrentSubjectResponse(BaseModel):
    conversation_id: str
    state: ConversationState
