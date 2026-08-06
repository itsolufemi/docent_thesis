from uuid import uuid4

from conversation_core.schemas.conversation_schemas import (
    ConversationState,
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
    *,
    user: str | None = None,
    assistant: str | None = None,
    previous_subject: list[str] | None = None,
    subject: list[str] | None = None,
    reference: list[str] | None = None,
) -> DialogueTurn | None:
    """Append one complete or pending user-assistant exchange."""
    state = get_conversation(conversation_id)

    if state is None:
        return None

    turn = DialogueTurn(
        previous_subject=previous_subject or [],
        subject=subject or [],
        reference=reference or [],
        user=user,
        assistant=assistant,
    )

    state.dialogue_history.append(turn)
    conversations[conversation_id] = state

    if assistant is not None or user is None:
        append_dialogue_turn_log(
            conversation_id=conversation_id,
            turn=turn,
        )

    return turn


def complete_dialogue_turn(
    conversation_id: str,
    turn: DialogueTurn,
    *,
    assistant: str,
) -> DialogueTurn | None:
    """Complete an exchange that was added before response generation."""
    state = get_conversation(conversation_id)

    if state is None or turn not in state.dialogue_history:
        return None

    turn.assistant = assistant
    conversations[conversation_id] = state

    append_dialogue_turn_log(
        conversation_id=conversation_id,
        turn=turn,
    )

    return turn


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
