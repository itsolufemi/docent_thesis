from fastapi import APIRouter, Cookie, HTTPException

from conversation_core.memory.conversation_store import (
    create_conversation,
    get_conversation,
    set_active_branch_subject,
)

from conversation_core.schemas.conversation_schemas import (
    ConversationState,
    StartConversationResponse,
    SetCurrentSubjectRequest,
    SetCurrentSubjectResponse,
)

router = APIRouter()

CONVERSATION_COOKIE_NAME = "conversation_id"

@router.post("/api/conversations/start", response_model=StartConversationResponse)
def start_conversation():
    state = create_conversation()

    return StartConversationResponse(
        conversation_id=state.conversation_id,
        state=state
    )

@router.get(
    "/api/conversations/current",
    response_model=ConversationState,
)
def read_current_conversation(
    conversation_id: str | None = Cookie(
        default=None,
    ),
):
    if conversation_id is None:
        raise HTTPException(
            status_code=404,
            detail="No active conversation cookie found.",
        )

    state = get_conversation(
        conversation_id
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    return state


@router.post(
    "/api/conversations/current/active-branch/subject",
    response_model=SetCurrentSubjectResponse,
)
def update_active_branch_subject(
    request: SetCurrentSubjectRequest,
    conversation_id: str | None = Cookie(
        default=None,
    ),
):
    if conversation_id is None:
        raise HTTPException(
            status_code=404,
            detail="No active conversation cookie found.",
        )

    state = set_active_branch_subject(
        conversation_id=conversation_id,
        subject_reference=request.subject_reference,
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation or active branch not found.",
        )
    
    return SetCurrentSubjectResponse(
        conversation_id=conversation_id,
        state=state,
    )
