from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect

from conversation_core.api.routes_query import (
    CONVERSATION_COOKIE_NAME,
)
from conversation_core.memory.conversation_store import (
    create_conversation,
    get_conversation,
)
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.services.query_service import (
    QueryEngine,
    default_query_engine,
)
from conversation_core.services.turn_buffer_service import (
    process_turn_event,
)


UtteranceClassifier = Callable[
    [str, bool],
    UtteranceRoute,
]


def _conversation_cookie_header(
    conversation_id: str,
) -> tuple[bytes, bytes]:
    cookie = (
        f"{CONVERSATION_COOKIE_NAME}={conversation_id}; "
        "HttpOnly; Path=/; SameSite=lax"
    )
    return b"set-cookie", cookie.encode("latin-1")


async def process_streamed_turn_event(
    *,
    websocket: WebSocket,
    request_id: str,
    conversation_id: str,
    payload: dict,
    query_engine: QueryEngine,
    utterance_classifier: UtteranceClassifier | None,
) -> None:
    try:
        event = TurnBufferEvent(
            conversation_id=conversation_id,
            partial_utterance=str(
                payload.get(
                    "partial_utterance",
                    "",
                )
            ),
            is_speech_active=bool(
                payload.get(
                    "is_speech_active",
                    False,
                )
            ),
            silence_duration_ms=int(
                payload.get(
                    "silence_duration_ms",
                    0,
                )
            ),
            assistant_was_speaking=bool(
                payload.get(
                    "assistant_was_speaking",
                    False,
                )
            ),
        )

        turn_result = await asyncio.to_thread(
            process_turn_event,
            event,
        )

        await websocket.send_json(
            {
                "type": "turn_evaluated",
                "request_id": request_id,
                "payload": turn_result.model_dump(
                    mode="json"
                ),
            }
        )

        if not turn_result.should_finalise_turn:
            return

        finalised_utterance = (
            turn_result.finalised_utterance
        )

        if not finalised_utterance:
            return

        utterance_route = None

        if utterance_classifier is not None:
            utterance_route = await asyncio.to_thread(
                utterance_classifier,
                finalised_utterance,
                event.assistant_was_speaking,
            )

            await websocket.send_json(
                {
                    "type": "utterance_classified",
                    "request_id": request_id,
                    "payload": (
                        utterance_route.model_dump(
                            mode="json"
                        )
                    ),
                }
            )

        await websocket.send_json(
            {
                "type": "query_started",
                "request_id": request_id,
                "payload": {
                    "utterance": finalised_utterance,
                },
            }
        )

        query_result = await asyncio.to_thread(
            query_engine.generate_response,
            text=finalised_utterance,
            conversation_id=conversation_id,
            subject_reference=None,
            utterance_route=utterance_route,
            include_debug=bool(
                payload.get("debug", False)
            ),
        )

        await websocket.send_json(
            {
                "type": "query_complete",
                "request_id": request_id,
                "payload": query_result.model_dump(
                    mode="json"
                ),
            }
        )
    except Exception as error:
        await websocket.send_json(
            {
                "type": "turn_error",
                "request_id": request_id,
                "payload": {
                    "detail": str(error),
                },
            }
        )


def create_turn_buffer_stream_router(
    query_engine: QueryEngine | None = None,
    utterance_classifier: UtteranceClassifier | None = None,
) -> APIRouter:
    router = APIRouter()
    active_query_engine = (
        query_engine or default_query_engine
    )

    @router.websocket(
        "/api/conversation/turn-buffer/stream"
    )
    async def stream_turn_processing(
        websocket: WebSocket,
    ) -> None:
        conversation_id = websocket.cookies.get(
            CONVERSATION_COOKIE_NAME
        )
        set_conversation_cookie = False

        if (
            conversation_id is None
            or get_conversation(conversation_id) is None
        ):
            conversation = create_conversation()
            conversation_id = conversation.conversation_id
            set_conversation_cookie = True

        accept_headers = []

        if set_conversation_cookie:
            accept_headers.append(
                _conversation_cookie_header(
                    conversation_id
                )
            )

        await websocket.accept(
            headers=accept_headers,
        )

        await websocket.send_json(
            {
                "type": "turn_stream_ready",
                "payload": {
                    "conversation_id": conversation_id,
                },
            }
        )

        try:
            while True:
                message = await websocket.receive_json()

                if message.get("type") != "turn_event":
                    await websocket.send_json(
                        {
                            "type": "turn_error",
                            "request_id": message.get(
                                "request_id"
                            ),
                            "payload": {
                                "detail": (
                                    "Expected a "
                                    "turn_event message."
                                ),
                            },
                        }
                    )
                    continue

                request_id = (
                    message.get("request_id")
                    or str(uuid4())
                )
                payload = message.get("payload")

                if not isinstance(payload, dict):
                    payload = {}

                await process_streamed_turn_event(
                    websocket=websocket,
                    request_id=str(request_id),
                    conversation_id=conversation_id,
                    payload=payload,
                    query_engine=active_query_engine,
                    utterance_classifier=(
                        utterance_classifier
                    ),
                )
        except WebSocketDisconnect:
            return

    return router
