from __future__ import annotations

import asyncio
from collections.abc import Iterator
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect

from conversation_core.services.google_tts_service import (
    DEFAULT_LANGUAGE_CODE,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_VOICE_NAME,
    GoogleTextToSpeechService,
    google_tts_service,
)


def _next_audio_chunk(
    iterator: Iterator[bytes],
) -> bytes | None:
    """
    Return the next Google audio chunk.

    StopIteration must not escape through
    asyncio.to_thread(), because asyncio cannot safely
    propagate StopIteration through a Future.
    """
    try:
        return next(iterator)
    except StopIteration:
        return None


def create_tts_stream_router(
    tts_service: GoogleTextToSpeechService | None = None,
) -> APIRouter:
    router = APIRouter()
    active_tts_service = (
        tts_service or google_tts_service
    )

    @router.websocket("/api/tts/stream")
    async def stream_speech(
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()

        stream_id: str | None = None

        try:
            request = await websocket.receive_json()

            if request.get("type") != "synthesise":
                await websocket.send_json({
                    "type": "tts_error",
                    "payload": {
                        "detail": (
                            "First message must be a "
                            "synthesise request."
                        ),
                    },
                })
                await websocket.close(code=1008)
                return

            payload = request.get(
                "payload",
                {},
            )
            text = str(
                payload.get("text", "")
            ).strip()
            voice_name = (
                payload.get("voice_name")
                or DEFAULT_VOICE_NAME
            )
            language_code = (
                payload.get("language_code")
                or DEFAULT_LANGUAGE_CODE
            )

            if not text:
                await websocket.send_json({
                    "type": "tts_error",
                    "payload": {
                        "detail": (
                            "Text-to-speech input "
                            "cannot be empty."
                        ),
                    },
                })
                await websocket.close(code=1008)
                return

            if len(text) > 5_000:
                await websocket.send_json({
                    "type": "tts_error",
                    "payload": {
                        "detail": (
                            "Text-to-speech input "
                            "exceeds 5,000 characters."
                        ),
                    },
                })
                await websocket.close(code=1008)
                return

            stream_id = str(uuid4())
            started_at = perf_counter()

            await websocket.send_json({
                "type": "tts_started",
                "payload": {
                    "stream_id": stream_id,
                    "voice_name": voice_name,
                    "language_code": (
                        language_code
                    ),
                    "sample_rate": (
                        DEFAULT_SAMPLE_RATE
                    ),
                    "encoding": "pcm_s16le",
                    "character_count": len(text),
                },
            })

            iterator = (
                active_tts_service
                .stream_synthesise(
                    text,
                    voice_name=voice_name,
                    language_code=language_code,
                )
            )

            chunk_index = 0
            audio_bytes = 0
            first_chunk_seconds: float | None = None

            while True:
                chunk = await asyncio.to_thread(
                    _next_audio_chunk,
                    iterator,
                )

                if chunk is None:
                    break

                is_first_chunk = chunk_index == 0

                if is_first_chunk:
                    first_chunk_seconds = (
                        perf_counter() - started_at
                    )

                await websocket.send_json({
                    "type": "tts_chunk",
                    "payload": {
                        "stream_id": stream_id,
                        "chunk_index": chunk_index,
                        "byte_length": len(chunk),
                        "first_chunk": is_first_chunk,
                        "request_to_first_chunk_seconds": (
                            round(
                                first_chunk_seconds,
                                4,
                            )
                            if is_first_chunk
                            and first_chunk_seconds is not None
                            else None
                        ),
                    },
                })

                await websocket.send_bytes(chunk)

                audio_bytes += len(chunk)
                chunk_index += 1

            elapsed_seconds = (
                perf_counter() - started_at
            )

            await websocket.send_json({
                "type": "tts_complete",
                "payload": {
                    "stream_id": stream_id,
                    "chunk_count": chunk_index,
                    "audio_bytes": audio_bytes,
                    "generation_seconds": round(
                        elapsed_seconds,
                        4,
                    ),
                    "first_chunk_seconds": (
                        round(
                            first_chunk_seconds,
                            4,
                        )
                        if first_chunk_seconds is not None
                        else None
                    ),
                },
            })

        except WebSocketDisconnect:
            return
        except Exception as error:
            try:
                await websocket.send_json({
                    "type": "tts_error",
                    "payload": {
                        "stream_id": stream_id,
                        "detail": str(error),
                    },
                })
            except Exception:
                pass

        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    return router
