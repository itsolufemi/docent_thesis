import asyncio
import json
from collections.abc import Coroutine
from typing import Any

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.concurrency import run_in_threadpool

from conversation_core.services.audio_stream_service import (
    AudioStreamBuffer,
)
from conversation_core.services.transcription_service import (
    TranscriptionService,
    default_transcription_service,
)


DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
PCM16_SAMPLE_WIDTH_BYTES = 2

MAX_SEGMENT_BYTES = 30 * 1024 * 1024


def create_audio_stream_router(
    transcription_service: TranscriptionService | None = None,
) -> APIRouter:
    router = APIRouter()
    active_transcription_service = (
        transcription_service
        or default_transcription_service
    )

    @router.websocket("/api/audio/stream")
    async def stream_audio(
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()

        active_segment_id: str | None = None
        active_buffer: AudioStreamBuffer | None = None
        known_segment_ids: set[str] = set()
        transcription_tasks: set[asyncio.Task[None]] = set()
        send_lock = asyncio.Lock()
        connection_open = True

        async def send_message(
            message_type: str,
            payload: dict[str, Any],
        ) -> None:
            if not connection_open:
                return

            async with send_lock:
                if connection_open:
                    await websocket.send_json(
                        {
                            "type": message_type,
                            "payload": payload,
                        }
                    )

        async def send_audio_error(
            detail: str,
            *,
            segment_id: str | None = None,
        ) -> None:
            payload: dict[str, Any] = {
                "detail": detail,
            }

            if segment_id is not None:
                payload["segment_id"] = segment_id

            await send_message(
                "audio_error",
                payload,
            )

        async def transcribe_segment(
            *,
            segment_id: str,
            audio_buffer: AudioStreamBuffer,
            silence_duration_ms: int,
        ) -> None:
            summary = audio_buffer.summary()
            pcm_bytes = audio_buffer.to_bytes()

            try:
                transcription = await run_in_threadpool(
                    (
                        active_transcription_service
                        .transcribe_pcm16
                    ),
                    pcm_bytes,
                    sample_rate=audio_buffer.sample_rate,
                    channels=audio_buffer.channels,
                )
            except asyncio.CancelledError:
                raise
            except ValueError as error:
                await send_audio_error(
                    str(error),
                    segment_id=segment_id,
                )
                return
            except Exception as error:
                await send_audio_error(
                    (
                        "The audio could not be "
                        f"transcribed: {error}"
                    ),
                    segment_id=segment_id,
                )
                return

            await send_message(
                "audio_transcription",
                {
                    "segment_id": segment_id,
                    "silence_duration_ms": (
                        silence_duration_ms
                    ),
                    "stream": summary.model_dump(),
                    "transcription": (
                        transcription.model_dump()
                    ),
                },
            )

        def start_background_task(
            coroutine: Coroutine[Any, Any, None],
        ) -> None:
            task = asyncio.create_task(coroutine)
            transcription_tasks.add(task)
            task.add_done_callback(
                transcription_tasks.discard
            )

        try:
            while True:
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                binary_chunk = message.get("bytes")

                if binary_chunk is not None:
                    if active_buffer is None:
                        await send_audio_error(
                            "No active audio segment exists.",
                        )
                        continue

                    if (
                        active_buffer.total_bytes
                        + len(binary_chunk)
                        > MAX_SEGMENT_BYTES
                    ):
                        await send_audio_error(
                            (
                                "Audio segment exceeded the maximum "
                                "permitted size."
                            ),
                            segment_id=active_segment_id,
                        )
                        await websocket.close(
                            code=1009,
                            reason="Audio segment too large.",
                        )
                        return

                    active_buffer.append(binary_chunk)
                    continue

                text_message = message.get("text")

                if text_message is None:
                    continue

                try:
                    event = json.loads(text_message)
                except json.JSONDecodeError:
                    await send_audio_error(
                        "Invalid JSON control message.",
                    )
                    continue

                event_type = event.get("type")
                payload = event.get("payload") or {}

                if event_type == "start_segment":
                    segment_id_value = payload.get("segment_id")

                    if (
                        not isinstance(segment_id_value, str)
                        or not segment_id_value.strip()
                    ):
                        await send_audio_error(
                            "A non-empty segment_id is required.",
                        )
                        continue

                    segment_id = segment_id_value.strip()

                    if active_buffer is not None:
                        await send_audio_error(
                            (
                                "An audio segment is already "
                                "active."
                            ),
                            segment_id=active_segment_id,
                        )
                        continue

                    if segment_id in known_segment_ids:
                        await send_audio_error(
                            (
                                "The segment_id has already been "
                                "used on this connection."
                            ),
                            segment_id=segment_id,
                        )
                        continue

                    try:
                        sample_rate = int(
                            payload.get(
                                "sample_rate",
                                DEFAULT_SAMPLE_RATE,
                            )
                        )
                        channels = int(
                            payload.get(
                                "channels",
                                DEFAULT_CHANNELS,
                            )
                        )
                    except (TypeError, ValueError):
                        await send_audio_error(
                            (
                                "Sample rate and channels must be "
                                "positive integers."
                            ),
                            segment_id=segment_id,
                        )
                        continue

                    sample_format = payload.get(
                        "sample_format",
                        "pcm_s16le",
                    )

                    if sample_format != "pcm_s16le":
                        await send_audio_error(
                            "Only pcm_s16le is supported.",
                            segment_id=segment_id,
                        )
                        continue

                    if sample_rate <= 0 or channels <= 0:
                        await send_audio_error(
                            (
                                "Sample rate and channels must be "
                                "positive."
                            ),
                            segment_id=segment_id,
                        )
                        continue

                    active_segment_id = segment_id
                    active_buffer = AudioStreamBuffer(
                        sample_rate=sample_rate,
                        channels=channels,
                        sample_width_bytes=(
                            PCM16_SAMPLE_WIDTH_BYTES
                        ),
                    )
                    known_segment_ids.add(segment_id)

                    await send_message(
                        "audio_segment_started",
                        {
                            "segment_id": segment_id,
                            "sample_rate": sample_rate,
                            "channels": channels,
                            "sample_format": sample_format,
                        },
                    )

                elif event_type == "finalise_segment":
                    requested_segment_id = payload.get(
                        "segment_id"
                    )

                    if (
                        active_buffer is None
                        or active_segment_id is None
                    ):
                        await send_audio_error(
                            "No active audio segment exists.",
                            segment_id=(
                                requested_segment_id
                                if isinstance(
                                    requested_segment_id,
                                    str,
                                )
                                else None
                            ),
                        )
                        continue

                    if requested_segment_id != active_segment_id:
                        await send_audio_error(
                            (
                                "The segment_id does not match "
                                "the active audio segment."
                            ),
                            segment_id=(
                                requested_segment_id
                                if isinstance(
                                    requested_segment_id,
                                    str,
                                )
                                else None
                            ),
                        )
                        continue

                    try:
                        silence_duration_ms = int(
                            payload.get(
                                "silence_duration_ms",
                                0,
                            )
                        )
                    except (TypeError, ValueError):
                        await send_audio_error(
                            (
                                "silence_duration_ms must be a "
                                "non-negative integer."
                            ),
                            segment_id=active_segment_id,
                        )
                        continue

                    if silence_duration_ms < 0:
                        await send_audio_error(
                            (
                                "silence_duration_ms must be "
                                "non-negative."
                            ),
                            segment_id=active_segment_id,
                        )
                        continue

                    detached_segment_id = active_segment_id
                    detached_buffer = active_buffer
                    active_segment_id = None
                    active_buffer = None

                    if not detached_buffer.total_bytes:
                        await send_audio_error(
                            "No audio data was received.",
                            segment_id=detached_segment_id,
                        )
                        continue

                    summary = detached_buffer.summary()

                    await send_message(
                        "transcription_started",
                        {
                            "segment_id": detached_segment_id,
                            "silence_duration_ms": (
                                silence_duration_ms
                            ),
                            "duration_seconds": (
                                summary.duration_seconds
                            ),
                        },
                    )

                    start_background_task(
                        transcribe_segment(
                            segment_id=detached_segment_id,
                            audio_buffer=detached_buffer,
                            silence_duration_ms=(
                                silence_duration_ms
                            ),
                        )
                    )

                elif event_type == "cancel_segment":
                    requested_segment_id = payload.get(
                        "segment_id"
                    )

                    if (
                        active_buffer is None
                        or active_segment_id is None
                    ):
                        await send_audio_error(
                            "No active audio segment exists.",
                        )
                        continue

                    if requested_segment_id != active_segment_id:
                        await send_audio_error(
                            (
                                "The segment_id does not match "
                                "the active audio segment."
                            ),
                            segment_id=(
                                requested_segment_id
                                if isinstance(
                                    requested_segment_id,
                                    str,
                                )
                                else None
                            ),
                        )
                        continue

                    cancelled_segment_id = active_segment_id
                    active_segment_id = None
                    active_buffer = None

                    await send_message(
                        "audio_segment_cancelled",
                        {
                            "segment_id": (
                                cancelled_segment_id
                            ),
                        },
                    )

                else:
                    await send_audio_error(
                        f"Unknown audio event: {event_type}",
                    )

        except WebSocketDisconnect:
            pass
        finally:
            connection_open = False

            for task in transcription_tasks:
                task.cancel()

            if transcription_tasks:
                await asyncio.gather(
                    *transcription_tasks,
                    return_exceptions=True,
                )

    return router
