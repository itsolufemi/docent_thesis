from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import perf_counter
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
from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
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


def build_stream_websocket_message(
    *,
    request_id: str,
    event: LLMStreamEvent,
) -> dict:
    if event.event_type == "response_started":
        return {
            "type": "response_started",
            "request_id": request_id,
            "payload": {},
        }

    if event.event_type == "content_delta":
        return {
            "type": "response_delta",
            "request_id": request_id,
            "payload": {
                "text": event.text,
            },
        }

    if event.event_type == "tool_call":
        return {
            "type": "tool_call_started",
            "request_id": request_id,
            "payload": {
                "tool_calls": event.tool_calls,
            },
        }

    if event.event_type == "tool_result":
        return {
            "type": "tool_call_complete",
            "request_id": request_id,
            "payload": {
                "tool_name": event.tool_name,
                "result": event.tool_result,
            },
        }

    return {
        "type": "response_complete",
        "request_id": request_id,
        "payload": {
            "response": event.text,
        },
    }


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

        stream_queue: asyncio.Queue[
            LLMStreamEvent | None
        ] = asyncio.Queue()
        event_loop = asyncio.get_running_loop()

        def handle_stream_event(
            event: LLMStreamEvent,
        ) -> None:
            event_loop.call_soon_threadsafe(
                stream_queue.put_nowait,
                event,
            )

        async def run_query():
            try:
                return await asyncio.to_thread(
                    query_engine
                    .generate_streaming_response,
                    text=finalised_utterance,
                    conversation_id=conversation_id,
                    subject_reference=None,
                    utterance_route=utterance_route,
                    include_debug=bool(
                        payload.get(
                            "debug",
                            False,
                        )
                    ),
                    on_stream_event=(
                        handle_stream_event
                    ),
                )
            finally:
                await stream_queue.put(None)

        query_started_at = perf_counter()
        first_delta_sent = False
        query_task = asyncio.create_task(
            run_query()
        )

        try:
            while True:
                stream_event = (
                    await stream_queue.get()
                )

                if stream_event is None:
                    break

                if (
                    stream_event.event_type
                    == "content_delta"
                    and not first_delta_sent
                ):
                    first_delta_sent = True

                    await websocket.send_json(
                        {
                            "type": (
                                "response_first_delta"
                            ),
                            "request_id": request_id,
                            "payload": {
                                "seconds": round(
                                    perf_counter()
                                    - query_started_at,
                                    4,
                                ),
                            },
                        }
                    )

                await websocket.send_json(
                    build_stream_websocket_message(
                        request_id=request_id,
                        event=stream_event,
                    )
                )

            query_result = await query_task
        finally:
            if not query_task.done():
                query_task.cancel()

        await websocket.send_json(
            {
                "type": "query_complete",
                "request_id": request_id,
                "payload": query_result.model_dump(
                    mode="json"
                ),
            }
        )
    except WebSocketDisconnect:
        return
    except Exception as error:
        try:
            await websocket.send_json(
                {
                    "type": "turn_error",
                    "request_id": request_id,
                    "payload": {
                        "detail": str(error),
                    },
                }
            )
        except (WebSocketDisconnect, RuntimeError):
            return


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
