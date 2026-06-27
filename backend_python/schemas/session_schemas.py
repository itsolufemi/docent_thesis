from typing import Literal
from pydantic import BaseModel, Field

dialogue_role = Literal["user", "assistant", "system"]

class DialogueTurn(BaseModel):
    role: dialogue_role
    content: str

class SessionState(BaseModel):
    session_id: str
    current_painting_index: int | None = None
    previous_painting_index: int | None = None
    visited_painting_indexes: list[int] = Field(default_factory=list)
    dialogue_history: list[DialogueTurn] = Field(default_factory=list)


class StartSessionResponse(BaseModel):
    session_id: str
    state: SessionState

class SetCurrentPaintingRequest(BaseModel):
    painting_index:int

class SetCurrentPaintingResponse(BaseModel):
    session_id: str
    state: SessionState
