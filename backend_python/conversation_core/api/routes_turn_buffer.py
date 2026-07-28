from collections.abc import Callable

from fastapi import APIRouter, Cookie, Response

from conversation_core.api.routes_query import CONVERSATION_COOKIE_NAME
from conversation_core.memory.conversation_store import (
    create_conversation,
    get_conversation,
)
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
    TurnBufferEventRequest,
    TurnProcessingResult,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.services.query_service import (
    QueryEngine,
    default_query_engine,
)
from conversation_core.services.turn_processing_service import (
    process_conversation_turn,
)

UtteranceClassifier = Callable[
    [str, bool],
    UtteranceRoute,
]


def create_turn_buffer_router(
    query_engine: QueryEngine | None = None,
    utterance_classifier: UtteranceClassifier | None = None,
) -> APIRouter:
    router = APIRouter()
    active_query_engine = query_engine or default_query_engine

    @router.post(
        "/api/conversation/turn-buffer/event",
        response_model=TurnProcessingResult,
    )
    def receive_turn_buffer_event(
        request: TurnBufferEventRequest,
        response: Response,
        conversation_id: str | None = Cookie(
            default=None,
            alias=CONVERSATION_COOKIE_NAME,
        ),
    ) -> TurnProcessingResult:
        active_conversation_id = conversation_id

        if (
            active_conversation_id is None
            or get_conversation(active_conversation_id) is None
        ):
            conversation = create_conversation()
            active_conversation_id = conversation.conversation_id

            response.set_cookie(
                key=CONVERSATION_COOKIE_NAME,
                value=active_conversation_id,
                httponly=True,
                samesite="lax",
                secure=False,
            )

        event = TurnBufferEvent(
            conversation_id=active_conversation_id,
            partial_utterance=request.partial_utterance,
            is_speech_active=request.is_speech_active,
            silence_duration_ms=request.silence_duration_ms,
            assistant_was_speaking=(
                request.assistant_was_speaking
            ),
        )

        return process_conversation_turn(
            event=event,
            query_engine=active_query_engine,
            utterance_classifier=utterance_classifier,
            include_debug=request.debug,
        )

    return router
