from fastapi import APIRouter

from core_engine.schemas.turn_detection_schemas import (
    TurnDetectionRequest,
    TurnDetectionResult,
)
from core_engine.services.turn_detection_service import (
    detect_turn_completion,
)


router = APIRouter()


@router.post(
    "/api/conversation/turn-detection",
    response_model=TurnDetectionResult,
)
def read_turn_detection(
    request: TurnDetectionRequest,
) -> TurnDetectionResult:
    return detect_turn_completion(
        partial_utterance=request.partial_utterance,
        is_speech_active=request.is_speech_active,
        silence_duration_ms=request.silence_duration_ms,
        previous_turns=request.previous_turns,
    )
