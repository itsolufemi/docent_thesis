from __future__ import annotations

import asyncio
from collections.abc import Iterator
from threading import Event
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect

from conversation_core.services.tts_service import (
    TextToSpeechService,
)
from conversation_core.services.tts_service_factory import (
    default_tts_service,
)


def _next_audio_chunk(
    iterator: Iterator[bytes],
) -> bytes | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def create_tts_stream_router(
    tts_service: TextToSpeechService | None = None,
) -> APIRouter:
    router = APIRouter()
    active_tts_service = tts_service or default_tts_service

    @router.websocket("/api/tts/stream")
    async def stream_speech(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()
        active_task: asyncio.Task | None = None
        active_synthesis_id: str | None = None
        cancellation_event: Event | None = None

        async def send_json(message: dict) -> None:
            async with send_lock:
                await websocket.send_json(message)

        async def send_audio_chunk(
            metadata: dict,
            audio: bytes,
        ) -> None:
            async with send_lock:
                await websocket.send_json(metadata)
                await websocket.send_bytes(audio)

        async def run_synthesis(
            *,
            synthesis_id: str,
            text: str,
            voice_name: str,
            language_code: str,
            cancelled: Event,
        ) -> None:
            started_at = perf_counter()
            iterator: Iterator[bytes] | None = None

            try:
                await send_json({
                    "type": "tts_started",
                    "payload": {
                        "synthesis_id": synthesis_id,
                        "stream_id": synthesis_id,
                        "provider": (
                            active_tts_service.provider_name
                        ),
                        "voice_name": voice_name,
                        "language_code": language_code,
                        "sample_rate": (
                            active_tts_service.sample_rate
                        ),
                        "encoding": "pcm_s16le",
                        "character_count": len(text),
                    },
                })
                iterator = active_tts_service.stream_synthesise(
                    text,
                    voice_name=voice_name,
                    language_code=language_code,
                )
                chunk_index = 0
                audio_bytes = 0
                first_chunk_seconds: float | None = None

                while not cancelled.is_set():
                    chunk = await asyncio.to_thread(
                        _next_audio_chunk,
                        iterator,
                    )

                    if chunk is None or cancelled.is_set():
                        break

                    is_first_chunk = chunk_index == 0

                    if is_first_chunk:
                        first_chunk_seconds = (
                            perf_counter() - started_at
                        )

                    await send_audio_chunk(
                        {
                            "type": "tts_chunk",
                            "payload": {
                                "synthesis_id": synthesis_id,
                                "stream_id": synthesis_id,
                                "chunk_index": chunk_index,
                                "byte_length": len(chunk),
                                "first_chunk": is_first_chunk,
                                "request_to_first_chunk_seconds": (
                                    round(first_chunk_seconds, 4)
                                    if is_first_chunk
                                    and first_chunk_seconds is not None
                                    else None
                                ),
                            },
                        },
                        chunk,
                    )
                    audio_bytes += len(chunk)
                    chunk_index += 1

                if cancelled.is_set():
                    return

                await send_json({
                    "type": "tts_complete",
                    "payload": {
                        "synthesis_id": synthesis_id,
                        "stream_id": synthesis_id,
                        "chunk_count": chunk_index,
                        "audio_bytes": audio_bytes,
                        "generation_seconds": round(
                            perf_counter() - started_at,
                            4,
                        ),
                        "first_chunk_seconds": (
                            round(first_chunk_seconds, 4)
                            if first_chunk_seconds is not None
                            else None
                        ),
                    },
                })
            except asyncio.CancelledError:
                cancelled.set()
                raise
            except Exception as error:
                if not cancelled.is_set():
                    await send_json({
                        "type": "tts_error",
                        "payload": {
                            "synthesis_id": synthesis_id,
                            "stream_id": synthesis_id,
                            "detail": str(error),
                        },
                    })
            finally:
                close_iterator = getattr(iterator, "close", None)

                if callable(close_iterator):
                    close_iterator()

        await send_json({
            "type": "tts_ready",
            "payload": {
                "provider": active_tts_service.provider_name,
                "sample_rate": active_tts_service.sample_rate,
                "voice_name": (
                    active_tts_service.default_voice_name
                ),
                "language_code": (
                    active_tts_service.default_language_code
                ),
                "encoding": "pcm_s16le",
            },
        })

        try:
            while True:
                request = await websocket.receive_json()
                request_type = request.get("type")
                payload = request.get("payload") or {}

                if request_type == "cancel":
                    requested_id = payload.get("synthesis_id")

                    if (
                        cancellation_event is not None
                        and requested_id == active_synthesis_id
                        and active_task is not None
                        and not active_task.done()
                    ):
                        cancellation_event.set()
                        await send_json({
                            "type": "tts_cancelled",
                            "payload": {
                                "synthesis_id": requested_id,
                                "stream_id": requested_id,
                            },
                        })
                    continue

                if request_type != "synthesise":
                    await send_json({
                        "type": "tts_error",
                        "payload": {
                            "detail": (
                                "Message type must be synthesise "
                                "or cancel."
                            ),
                        },
                    })
                    continue

                if active_task is not None and not active_task.done():
                    if (
                        cancellation_event is not None
                        and cancellation_event.is_set()
                    ):
                        try:
                            await active_task
                        except (
                            asyncio.CancelledError,
                            Exception,
                        ):
                            pass
                    else:
                        await send_json({
                            "type": "tts_error",
                            "payload": {
                                "synthesis_id": payload.get(
                                    "synthesis_id"
                                ),
                                "detail": (
                                    "A synthesis request is already active."
                                ),
                            },
                        })
                        continue

                text = str(payload.get("text", "")).strip()
                synthesis_id = str(
                    payload.get("synthesis_id") or uuid4()
                )

                if not text or len(text) > 5_000:
                    detail = (
                        "Text-to-speech input cannot be empty."
                        if not text
                        else (
                            "Text-to-speech input exceeds "
                            "5,000 characters."
                        )
                    )
                    await send_json({
                        "type": "tts_error",
                        "payload": {
                            "synthesis_id": synthesis_id,
                            "detail": detail,
                        },
                    })
                    continue

                voice_name = str(
                    payload.get("voice_name")
                    or active_tts_service.default_voice_name
                )
                language_code = str(
                    payload.get("language_code")
                    or active_tts_service.default_language_code
                )
                cancellation_event = Event()
                active_synthesis_id = synthesis_id
                active_task = asyncio.create_task(
                    run_synthesis(
                        synthesis_id=synthesis_id,
                        text=text,
                        voice_name=voice_name,
                        language_code=language_code,
                        cancelled=cancellation_event,
                    )
                )
        except WebSocketDisconnect:
            pass
        finally:
            if cancellation_event is not None:
                cancellation_event.set()

            if active_task is not None and not active_task.done():
                active_task.cancel()

                try:
                    await active_task
                except (asyncio.CancelledError, Exception):
                    pass

    return router
