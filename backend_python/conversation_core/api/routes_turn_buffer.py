from fastapi import APIRouter

from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
    TurnBufferResult,
)
from conversation_core.services.turn_buffer_service import process_turn_event


router = APIRouter()


@router.post(
    "/api/conversation/turn-buffer/event",
    response_model=TurnBufferResult,
)
def receive_turn_buffer_event(
    event: TurnBufferEvent,
) -> TurnBufferResult:
    return process_turn_event(event)
