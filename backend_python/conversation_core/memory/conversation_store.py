from uuid import uuid4

from conversation_core.schemas.conversation_schemas import (
    ConversationState,
    DialogueTurn,
)
from conversation_core.services.conversation_log_service import (
    rewrite_dialogue_log,
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
    request_id: str | None = None,
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
        request_id=request_id,
    )

    state.dialogue_history.append(turn)
    conversations[conversation_id] = state

    rewrite_dialogue_log(
        conversation_id=conversation_id,
        dialogue_history=state.dialogue_history,
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

    rewrite_dialogue_log(
        conversation_id=conversation_id,
        dialogue_history=state.dialogue_history,
    )

    return turn


def update_dialogue_turn_context(
    conversation_id: str,
    turn: DialogueTurn,
    *,
    subject: list[str],
    reference: list[str],
    route_type: str | None,
) -> DialogueTurn | None:
    """Enrich an existing user turn after context resolution."""
    state = get_conversation(conversation_id)

    if state is None or turn not in state.dialogue_history:
        return None

    turn.subject = list(subject)
    turn.reference = list(reference)
    turn.route_type = route_type

    conversations[conversation_id] = state

    rewrite_dialogue_log(
        conversation_id=conversation_id,
        dialogue_history=state.dialogue_history,
    )

    return turn


def mark_dialogue_turn_interrupted(
    conversation_id: str,
    turn: DialogueTurn,
) -> DialogueTurn | None:
    """Record that generation for an otherwise valid turn was interrupted."""
    state = get_conversation(conversation_id)

    if state is None or turn not in state.dialogue_history:
        return None

    if not (
        turn.assistant
        and turn.assistant.rstrip().endswith(
            "[interrupted]"
        )
    ):
        turn.assistant = "[interrupted]"
    conversations[conversation_id] = state

    rewrite_dialogue_log(
        conversation_id=conversation_id,
        dialogue_history=state.dialogue_history,
    )

    return turn


def update_interrupted_assistant_response(
    conversation_id: str,
    request_id: str,
    assistant_text: str,
) -> DialogueTurn | None:
    """Correct one generated response to what playback actually delivered."""
    state = get_conversation(conversation_id)

    if state is None:
        return None

    corrected_text = assistant_text.strip()

    if not corrected_text:
        return None

    for turn in reversed(state.dialogue_history):
        if turn.request_id != request_id:
            continue

        turn.assistant = corrected_text
        conversations[conversation_id] = state
        rewrite_dialogue_log(
            conversation_id=conversation_id,
            dialogue_history=state.dialogue_history,
        )
        return turn

    return None


def build_history_with_playback_interruption(
    dialogue_history: list[DialogueTurn],
    *,
    request_id: str | None,
    assistant_text: str | None,
) -> list[DialogueTurn]:
    """Return a provisional history without mutating canonical turns."""
    history = [
        turn.model_copy(deep=True)
        for turn in dialogue_history
    ]

    if not request_id or not assistant_text:
        return history

    for turn in reversed(history):
        if turn.request_id == request_id:
            turn.assistant = assistant_text
            break

    return history


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
