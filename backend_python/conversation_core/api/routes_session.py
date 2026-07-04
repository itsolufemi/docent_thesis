from fastapi import APIRouter, HTTPException

from backend_python.conversation_core.memory.conversation_store import (
    create_session,
    get_session,
    set_current_painting
)

from backend_python.conversation_core.schemas.conversation_schemas import (
    SessionState,
    StartSessionResponse,
    SetCurrentPaintingRequest,
    SetCurrentPaintingResponse
)

router = APIRouter()

@router.post("/api/session/start", response_model=StartSessionResponse)
def start_session():
    state = create_session()

    return StartSessionResponse(
        session_id=state.session_id,
        state=state
    )

@router.get("/api/session/{session_id}", response_model=SessionState)

def read_session(session_id:str):
    state = get_session(session_id)

    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return state

@router.post(
    "/api/session/{session_id}/set/current_painting", 
    response_model=SetCurrentPaintingResponse
)

def update_current_painting(
    session_id:str,
    request: SetCurrentPaintingRequest
):
    state = set_current_painting(
        session_id=session_id,
        painting_index=request.painting_index
    )

    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SetCurrentPaintingResponse(
        session_id=session_id,
        state=state
    )