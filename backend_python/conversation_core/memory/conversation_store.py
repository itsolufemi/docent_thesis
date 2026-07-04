from uuid import uuid4

from backend_python.conversation_core.schemas.conversation_schemas import (
    DialogueRole, DialogueTurn, ConversationState
)

conversations: dict[str, ConversationState] = {}

def create_conversation() -> ConversationState:
    conversation_id = str(uuid4())
    
    state = ConversationState(
        conversation_id = conversation_id,
    )

    conversations[conversation_id] = state
    return state

def get_conversation(conversation_id:str) -> ConversationState | None:
    return conversations.get(conversation_id)

def set_current_subject(
        conversation_id:str,
        subject_reference: str,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None
    
    if state.current_subject is not None:
        state.previous_subject = state.current_subject

        if state.current_subject not in state.discussed_subjects:
            state.discussed_subjects.append(state.current_subject)

    state.current_subject = subject_reference

    conversations[conversation_id] = state

    return state

def add_dialogue_turn(
        conversation_id: str,
        role: DialogueRole,
        content: str,
    ) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None
    
    turn = DialogueTurn(
        role=role,
        content=content
    )

    state.dialogue_history.append(turn)

    conversations[conversation_id] = state

    return state

def get_recent_conversation_history(
    conversation_id: str,
    limit: int = 6,
) -> list[DialogueTurn]:
    state = get_conversation(conversation_id)

    if state is None:
        return []
    
    return state.dialogue_history[-limit:]


