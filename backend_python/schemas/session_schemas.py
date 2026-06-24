from pydantic import BaseModel

class SessionState(BaseModel):
    session_id: str
    current_painting_index: int | None = None
    previous_painting_index: int | None = None
    visited_painting_indexes: list[int] = []

class StartSessionResponse(BaseModel):
    session_id: str
    state: SessionState

class SetCurrentPaintingRequest(BaseModel):
    painting_index:int

class SetCurrentPaintingResponse(BaseModel):
    session_id: str
    state: SessionState
