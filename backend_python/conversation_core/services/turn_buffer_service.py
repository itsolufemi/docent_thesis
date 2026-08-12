from conversation_core.memory.conversation_store import (
    get_recent_conversation_history,
)
from conversation_core.memory.turn_buffer_store import turn_buffer_store
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
    TurnBufferResult,
    TurnBufferState,
)
from conversation_core.services.turn_detection_service import (
    FORCED_FINALISATION_SILENCE_MS,
    MIN_SEMANTIC_CHECK_SILENCE_MS,
    detect_turn_completion,
)


def snapshot_buffer(
    buffer: TurnBufferState,
) -> TurnBufferState:
    return buffer.model_copy(deep=True)


def finalise_buffer(
    event: TurnBufferEvent,
    buffer: TurnBufferState,
    reason: str,
) -> TurnBufferResult:
    completed_utterance = buffer.transcript
    buffer.is_finalised = True

    result = TurnBufferResult(
        state=snapshot_buffer(buffer),
        decision="finalise_turn",
        should_finalise_turn=True,
        finalised_utterance=completed_utterance,
        reason=reason,
    )

    turn_buffer_store.clear(event.conversation_id)
    return result


def process_turn_event(
    event: TurnBufferEvent,
) -> TurnBufferResult:
    buffer = turn_buffer_store.get_or_create(
        event.conversation_id
    )

    latest_transcript = event.partial_utterance.strip()

    buffer.transcript = latest_transcript
    buffer.is_speech_active = event.is_speech_active
    buffer.silence_duration_ms = event.silence_duration_ms

    if event.is_speech_active:
        buffer.is_finalised = False

        return TurnBufferResult(
            state=snapshot_buffer(buffer),
            decision="continue_listening",
            should_finalise_turn=False,
            reason="Speech is active and the buffer has been updated.",
        )

    if event.turn_completion_confirmed:
        return finalise_buffer(
            event=event,
            buffer=buffer,
            reason=(
                "Audio turn completion was confirmed before "
                "transcription."
            ),
        )

    already_evaluated = (
        buffer.last_evaluated_transcript == latest_transcript
    )
    semantic_pause_reached = (
        event.silence_duration_ms
        >= MIN_SEMANTIC_CHECK_SILENCE_MS
    )
    force_threshold_reached = (
        event.silence_duration_ms
        >= FORCED_FINALISATION_SILENCE_MS
    )

    if already_evaluated and force_threshold_reached:
        return finalise_buffer(
            event=event,
            buffer=buffer,
            reason=(
                "The unchanged utterance exceeded the maximum silence "
                "allowance after an incomplete TRP prediction."
            ),
        )

    if semantic_pause_reached and already_evaluated:
        return TurnBufferResult(
            state=snapshot_buffer(buffer),
            decision="await_more_speech",
            should_finalise_turn=False,
            reason=(
                "This transcript has already been evaluated during "
                "the current pause."
            ),
        )

    recent_turns = get_recent_conversation_history(
        conversation_id=event.conversation_id,
        limit=4,
    )
    previous_turns = [
        f"{turn.role}: {turn.content}"
        for turn in recent_turns
    ]

    detection = detect_turn_completion(
        partial_utterance=latest_transcript,
        is_speech_active=event.is_speech_active,
        silence_duration_ms=event.silence_duration_ms,
        previous_turns=previous_turns,
    )

    if detection.should_call_trp:
        buffer.last_evaluated_transcript = latest_transcript
        buffer.last_trp_probability = detection.trp_probability

    if detection.should_finalise_turn:
        return finalise_buffer(
            event=event,
            buffer=buffer,
            reason=detection.reason,
        )

    return TurnBufferResult(
        state=snapshot_buffer(buffer),
        decision=detection.decision,
        should_finalise_turn=False,
        reason=detection.reason,
    )
