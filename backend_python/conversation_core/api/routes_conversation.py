from fastapi import APIRouter, HTTPException

from backend_python.conversation_core.memory.conversation_store import (
    create_conversation,
    get_conversation,
    set_current_subject
)

from backend_python.conversation_core.schemas.conversation_schemas import (
    ConversationState,
    StartConversationResponse,
    SetCurrentSubjectRequest,
    SetCurrentSubjectResponse
)

router = APIRouter()

@router.post("/api/conversation/start", response_model=StartConversationResponse)
def start_conversation():
    state = create_conversation()

    return StartConversationResponse(
        conversation_id=state.conversation_id,
        state=state
    )

@router.get("/api/conversation/{conversation_id}", response_model=ConversationState)

def read_conversation(conversation_id:str):
    state = get_conversation(conversation_id)

    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return state

@router.post(
    "/api/conversation/{conversation_id}/set/current_subject", 
    response_model=SetCurrentSubjectResponse
)

def update_current_subject(
    conversation_id:str,
    request: SetCurrentSubjectRequest
):
    state = set_current_subject(
        conversation_id=conversation_id,
        subject_reference=request.subject_reference
    )

    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return SetCurrentSubjectResponse(
        conversation_id=conversation_id,
        state=state
    )