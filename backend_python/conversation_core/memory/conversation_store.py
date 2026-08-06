from uuid import uuid4

from conversation_core.schemas.conversation_schemas import (
    ConversationState,
    DialogueRole,
    DialogueTurn,
)
from conversation_core.services.conversation_log_service import (
    append_dialogue_turn_log,
)


conversations: dict[str, ConversationState] = {}

INTRODUCTION_TEXT_METADATA_KEY = "introduction_text"


def create_conversation() -> ConversationState:
    conversation_id = str(uuid4())

    state = ConversationState(
        conversation_id=conversation_id,
    )

    conversations[conversation_id] = state

    return state


def get_conversation(
    conversation_id: str,
) -> ConversationState | None:
    return conversations.get(conversation_id)


def add_dialogue_turn(
    conversation_id: str,
    role: DialogueRole,
    content: str,
    subjects: list[str] | None = None,
    previous_subject: str | None = None,
    current_subject: str | None = None,
    current_subject_reference: str | None = None,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    turn = DialogueTurn(
        role=role,
        content=content,
        subjects=subjects or [],
        previous_subject=previous_subject,
        current_subject=current_subject,
        current_subject_reference=(
            current_subject_reference
        ),
    )

    state.dialogue_history.append(turn)

    append_dialogue_turn_log(
        conversation_id=conversation_id,
        turn=turn,
    )

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


def get_conversation_introduction(
    conversation_id: str,
) -> str | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    introduction = state.metadata.get(
        INTRODUCTION_TEXT_METADATA_KEY
    )

    return (
        introduction
        if isinstance(introduction, str)
        else None
    )


def set_conversation_introduction(
    conversation_id: str,
    text: str,
) -> ConversationState | None:
    state = get_conversation(conversation_id)

    if state is None:
        return None

    state.metadata[
        INTRODUCTION_TEXT_METADATA_KEY
    ] = text

    conversations[conversation_id] = state

    return state
