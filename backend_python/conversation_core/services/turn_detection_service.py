from conversation_core.schemas.turn_detection_schemas import (
    TurnDetectionResult,
)
from conversation_core.services.trp_service import (
    predict_transition_relevance,
)


MIN_SEMANTIC_CHECK_SILENCE_MS = 300
FORCED_FINALISATION_SILENCE_MS = 1800


def detect_turn_completion(
    partial_utterance: str,
    is_speech_active: bool,
    silence_duration_ms: int,
    previous_turns: list[str] | None = None,
) -> TurnDetectionResult:
    cleaned_utterance = partial_utterance.strip()

    if is_speech_active:
        return TurnDetectionResult(
            decision="continue_listening",
            should_call_trp=False,
            should_finalise_turn=False,
            silence_duration_ms=silence_duration_ms,
            reason="Speech is still active.",
        )

    if not cleaned_utterance:
        return TurnDetectionResult(
            decision="continue_listening",
            should_call_trp=False,
            should_finalise_turn=False,
            silence_duration_ms=silence_duration_ms,
            reason="No linguistic content has been recognised.",
        )

    if silence_duration_ms < MIN_SEMANTIC_CHECK_SILENCE_MS:
        return TurnDetectionResult(
            decision="continue_listening",
            should_call_trp=False,
            should_finalise_turn=False,
            silence_duration_ms=silence_duration_ms,
            reason=(
                "The pause is too short to be treated as a candidate "
                "transition-relevance place."
            ),
        )

    prediction = predict_transition_relevance(
        partial_utterance=cleaned_utterance,
        previous_turns=previous_turns or [],
    )

    if prediction.turn_complete:
        return TurnDetectionResult(
            decision="finalise_turn",
            should_call_trp=True,
            should_finalise_turn=True,
            silence_duration_ms=silence_duration_ms,
            trp_probability=prediction.trp_probability,
            trp_prediction_seconds=prediction.prediction_seconds,
            reason=(
                "A pause occurred and the utterance was judged "
                "semantically complete."
            ),
        )

    if silence_duration_ms >= FORCED_FINALISATION_SILENCE_MS:
        return TurnDetectionResult(
            decision="finalise_turn",
            should_call_trp=True,
            should_finalise_turn=True,
            silence_duration_ms=silence_duration_ms,
            trp_probability=prediction.trp_probability,
            trp_prediction_seconds=prediction.prediction_seconds,
            reason=(
                "The semantic prediction was incomplete, but the maximum "
                "silence allowance was exceeded."
            ),
        )

    return TurnDetectionResult(
        decision="await_more_speech",
        should_call_trp=True,
        should_finalise_turn=False,
        silence_duration_ms=silence_duration_ms,
        trp_probability=prediction.trp_probability,
        trp_prediction_seconds=prediction.prediction_seconds,
        reason=(
            "A pause occurred, but the utterance still projects "
            "continuation."
        ),
    )
