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
from conversation_core.services.cancellation import (
    CancellationToken,
)
from conversation_core.services.turn_buffer_service import (
    process_turn_event,
)

from conversation_core.services.conversation_log_service import (
    append_telemetry_log,
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

    if event.event_type == "self_routing":
        return {
            "type": "self_routing",
            "request_id": request_id,
            "payload": {
                "valid": (
                    event.route_assessment
                    is not None
                ),
                "assessment": (
                    event.route_assessment
                ),
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

    if event.event_type == "response_cancelled":
        return {
            "type": "turn_cancelled",
            "request_id": request_id,
            "payload": {},
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
    cancellation_token: CancellationToken,
    send_lock: asyncio.Lock,
) -> None:
    async def send_message(
        message: dict,
    ) -> None:
        async with send_lock:
            await websocket.send_json(message)

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
            turn_completion_confirmed=bool(
                payload.get(
                    "turn_completion_confirmed",
                    False,
                )
            ),
        )

        turn_result = await asyncio.to_thread(
            process_turn_event,
            event,
        )

        await send_message(
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

            await send_message(
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

        await send_message(
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
                    cancellation_token=(
                        cancellation_token
                    ),
                )
            finally:
                await stream_queue.put(None)

        query_started_at = perf_counter()
        first_delta_sent = False
        cancellation_event_sent = False
        query_timing_events: list[dict] = []
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

                if stream_event.event_type == "timing":
                    query_timing_events.append(
                        {
                            "name": stream_event.timing_name,
                            "seconds": (
                                stream_event.timing_seconds
                            ),
                            **stream_event.timing_payload,
                        }
                    )
                    continue

                if (
                    stream_event.event_type
                    == "content_delta"
                    and not first_delta_sent
                ):
                    first_delta_sent = True

                    first_delta_seconds = (
                        perf_counter() - query_started_at
                    )

                    await send_message(
                        {
                            "type": (
                                "response_first_delta"
                            ),
                            "request_id": request_id,
                            "payload": {
                                "seconds": round(
                                    first_delta_seconds,
                                    4,
                                ),
                                "timings": (
                                    query_timing_events.copy()
                                ),
                            },
                        }
                    )

                stream_message = (
                    build_stream_websocket_message(
                        request_id=request_id,
                        event=stream_event,
                    )
                )

                if (
                    stream_event.event_type
                    == "response_cancelled"
                ):
                    cancellation_event_sent = True

                await send_message(
                    stream_message
                )

            query_result = await query_task
        finally:
            if not query_task.done():
                query_task.cancel()

        if cancellation_token.is_cancelled:
            if not cancellation_event_sent:
                await send_message(
                    {
                        "type": "turn_cancelled",
                        "request_id": request_id,
                        "payload": {},
                    }
                )

                append_telemetry_log(
                    conversation_id=conversation_id,
                    request_id=request_id,
                    event_type="backend_turn_cancelled",
                    payload={
                        "utterance": finalised_utterance,
                        "turn_evaluation": (
                            turn_result.model_dump(
                                mode="json"
                            )
                        ),
                        "utterance_route": (
                            utterance_route.model_dump(
                                mode="json"
                            )
                            if utterance_route is not None
                            else None
                        ),
                        "stream_timings": (
                            query_timing_events
                        ),
                    },
                )

            return

        append_telemetry_log(
            conversation_id=conversation_id,
            request_id=request_id,
            event_type="backend_turn_complete",
            payload={
                "utterance": finalised_utterance,
                "turn_evaluation": (
                    turn_result.model_dump(
                        mode="json"
                    )
                ),
                "utterance_route": (
                    utterance_route.model_dump(
                        mode="json"
                    )
                    if utterance_route is not None
                    else None
                ),
                "stream_timings": (
                    query_timing_events
                ),
                "query_result": (
                    query_result.model_dump(
                        mode="json"
                    )
                ),
            },
        )

        await send_message(
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
            await send_message(
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

        send_lock = asyncio.Lock()
        active_turn_tasks: dict[
            str,
            asyncio.Task[None],
        ] = {}
        cancellation_tokens: dict[
            str,
            CancellationToken,
        ] = {}

        async def send_message(
            message: dict,
        ) -> None:
            async with send_lock:
                await websocket.send_json(message)

        await send_message(
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
                message_type = message.get("type")

                if message_type == "client_telemetry":
                    request_id_value = message.get(
                        "request_id"
                    )
                    telemetry_payload = message.get(
                        "payload"
                    )

                    if (
                        not isinstance(
                            request_id_value,
                            str,
                        )
                        or not request_id_value
                        or not isinstance(
                            telemetry_payload,
                            dict,
                        )
                    ):
                        await send_message(
                            {
                                "type": "turn_error",
                                "request_id": (
                                    request_id_value
                                ),
                                "payload": {
                                    "detail": (
                                        "client_telemetry requires "
                                        "a request_id and object payload."
                                    ),
                                },
                            }
                        )
                        continue

                    append_telemetry_log(
                        conversation_id=conversation_id,
                        request_id=request_id_value,
                        event_type="client_voice_telemetry",
                        payload=telemetry_payload,
                    )

                    await send_message(
                        {
                            "type": (
                                "client_telemetry_recorded"
                            ),
                            "request_id": request_id_value,
                            "payload": {},
                        }
                    )
                    continue

                if message_type == "cancel_turn":
                    request_id_value = message.get(
                        "request_id"
                    )

                    if (
                        not isinstance(
                            request_id_value,
                            str,
                        )
                        or not request_id_value
                    ):
                        await send_message(
                            {
                                "type": "turn_error",
                                "request_id": None,
                                "payload": {
                                    "detail": (
                                        "cancel_turn requires "
                                        "a request_id."
                                    ),
                                },
                            }
                        )
                        continue

                    cancellation_token = (
                        cancellation_tokens.get(
                            request_id_value
                        )
                    )

                    if cancellation_token is not None:
                        cancellation_token.cancel()
                    else:
                        await send_message(
                            {
                                "type": "turn_cancelled",
                                "request_id": (
                                    request_id_value
                                ),
                                "payload": {
                                    "already_complete": True,
                                },
                            }
                        )

                    continue

                if message_type != "turn_event":
                    await send_message(
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

                request_id = str(request_id)
                cancellation_token = (
                    CancellationToken()
                )
                cancellation_tokens[request_id] = (
                    cancellation_token
                )

                task = asyncio.create_task(
                    process_streamed_turn_event(
                        websocket=websocket,
                        request_id=request_id,
                        conversation_id=(
                            conversation_id
                        ),
                        payload=payload,
                        query_engine=(
                            active_query_engine
                        ),
                        utterance_classifier=(
                            utterance_classifier
                        ),
                        cancellation_token=(
                            cancellation_token
                        ),
                        send_lock=send_lock,
                    )
                )
                active_turn_tasks[request_id] = task

                def remove_completed_task(
                    completed_task: asyncio.Task[None],
                    *,
                    completed_request_id: str = (
                        request_id
                    ),
                ) -> None:
                    active_turn_tasks.pop(
                        completed_request_id,
                        None,
                    )
                    cancellation_tokens.pop(
                        completed_request_id,
                        None,
                    )

                    if not completed_task.cancelled():
                        completed_task.exception()

                task.add_done_callback(
                    remove_completed_task
                )
        except WebSocketDisconnect:
            pass
        finally:
            for token in cancellation_tokens.values():
                token.cancel()

            for task in active_turn_tasks.values():
                task.cancel()

            if active_turn_tasks:
                await asyncio.gather(
                    *active_turn_tasks.values(),
                    return_exceptions=True,
                )

            cancellation_tokens.clear()
            active_turn_tasks.clear()

    return router
