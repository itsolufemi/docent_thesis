import asyncio
import json
import logging
from collections.abc import Coroutine
from time import perf_counter
from typing import Any

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.concurrency import run_in_threadpool

from conversation_core.schemas.smart_turn_schemas import (
    SmartTurnResult,
)
from conversation_core.services.audio_stream_service import (
    AudioStreamBuffer,
)
from conversation_core.services.smart_turn_service import (
    SmartTurnService,
)
from conversation_core.services.transcription_service import (
    TranscriptionService,
    default_transcription_service,
)

from conversation_core.services.moonshine_transcription_service import (
    MoonshineStreamingSession,
    MoonshineStreamingTranscriptionService,
)


DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
PCM16_SAMPLE_WIDTH_BYTES = 2
MAX_SEGMENT_BYTES = 30 * 1024 * 1024

logger = logging.getLogger(__name__)


def create_audio_stream_router(
    transcription_service: TranscriptionService | None = None,
    smart_turn_service: SmartTurnService | None = None,
    moonshine_transcription_service: (
        MoonshineStreamingTranscriptionService | None
    ) = None,
) -> APIRouter:    
    router = APIRouter()
    active_transcription_service = (
        transcription_service
        or default_transcription_service
    )

    active_moonshine_service = (
        moonshine_transcription_service
    )

    @router.websocket("/api/audio/stream")
    async def stream_audio(
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()

        active_segment_id: str | None = None
        active_buffer: AudioStreamBuffer | None = None
        active_candidate_id: int | None = None

        active_moonshine_session: (
            MoonshineStreamingSession | None
        ) = None

        known_segment_ids: set[str] = set()
        background_tasks: set[asyncio.Task[None]] = set()
        send_lock = asyncio.Lock()
        connection_open = True
        last_complete_candidate: dict[str, Any] | None = None

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
            candidate_id: int | None = None,
        ) -> None:
            payload: dict[str, Any] = {
                "detail": detail,
            }

            if segment_id is not None:
                payload["segment_id"] = segment_id

            if candidate_id is not None:
                payload["candidate_id"] = candidate_id

            await send_message(
                "audio_error",
                payload,
            )

        async def transcribe_segment(
            *,
            segment_id: str,
            audio_buffer: AudioStreamBuffer,
            moonshine_session: (
                MoonshineStreamingSession | None
            ),
            silence_duration_ms: int,
            forced_finalisation: bool,
            turn_completion_confirmed: bool,
            smart_turn_confirmed_at: float | None,
            finalisation_received_at: float,
        ) -> None:
            """
            Produce the final transcript for one completed audio segment.

            Moonshine is attempted first when a streaming session exists.
            The original PCM buffer remains available so Whisper can
            recover from an empty or failed Moonshine transcription.
            """

            summary = audio_buffer.summary()
            pcm_bytes = audio_buffer.to_bytes()

            transcription = None
            transcription_backend = "whisper"

            transcription_task_started_at = perf_counter()

            moonshine_finish_seconds: float | None = None
            whisper_transcription_seconds: float | None = None

            if moonshine_session is not None:
                try:
                    moonshine_started_at = perf_counter()

                    transcription = await run_in_threadpool(
                        moonshine_session.finish
                    )

                    moonshine_finish_seconds = (
                        perf_counter()
                        - moonshine_started_at
                    )

                    if transcription.text.strip():
                        transcription_backend = "moonshine"

                        logger.info(
                            "moonshine_transcription_complete %s",
                            json.dumps(
                                {
                                    "segment_id": segment_id,
                                    "seconds": round(
                                        moonshine_finish_seconds,
                                        4,
                                    ),
                                    "character_count": len(
                                        transcription.text
                                    ),
                                }
                            ),
                        )

                    else:
                        logger.warning(
                            "Moonshine returned an empty transcript "
                            "for segment %s. Falling back to Whisper.",
                            segment_id,
                        )

                        transcription = None

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "Moonshine transcription failed for "
                        "segment %s. Falling back to Whisper.",
                        segment_id,
                    )

                    transcription = None

            if transcription is None:
                try:
                    whisper_started_at = perf_counter()

                    transcription = await run_in_threadpool(
                        (
                            active_transcription_service
                            .transcribe_pcm16
                        ),
                        pcm_bytes,
                        sample_rate=audio_buffer.sample_rate,
                        channels=audio_buffer.channels,
                    )

                    whisper_transcription_seconds = (
                        perf_counter()
                        - whisper_started_at
                    )

                    transcription_backend = (
                        "whisper_fallback"
                        if moonshine_session is not None
                        else "whisper"
                    )

                    logger.info(
                        "whisper_transcription_complete %s",
                        json.dumps(
                            {
                                "segment_id": segment_id,
                                "seconds": round(
                                    whisper_transcription_seconds,
                                    4,
                                ),
                                "fallback": (
                                    moonshine_session
                                    is not None
                                ),
                                "character_count": len(
                                    transcription.text
                                ),
                            }
                        ),
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
                
            transcription_completed_at = perf_counter()

            timing = {
                "transcription_task_seconds": round(
                    transcription_completed_at
                    - transcription_task_started_at,
                    4,
                ),
                "finalisation_to_transcript_seconds": round(
                    transcription_completed_at
                    - finalisation_received_at,
                    4,
                ),
            }

            if smart_turn_confirmed_at is not None:
                timing[
                    "smart_turn_to_finalisation_seconds"
                ] = round(
                    finalisation_received_at
                    - smart_turn_confirmed_at,
                    4,
                )

                timing[
                    "smart_turn_to_transcript_seconds"
                ] = round(
                    transcription_completed_at
                    - smart_turn_confirmed_at,
                    4,
                )

            if moonshine_finish_seconds is not None:
                timing["moonshine_finish_seconds"] = round(
                    moonshine_finish_seconds,
                    4,
                )

            if whisper_transcription_seconds is not None:
                timing[
                    "whisper_transcription_seconds"
                ] = round(
                    whisper_transcription_seconds,
                    4,
                )

            logger.info(
                "transcription_pipeline_timing %s",
                json.dumps(
                    {
                        "segment_id": segment_id,
                        "backend": transcription_backend,
                        **timing,
                    }
                ),
            )

            await send_message(
                "audio_transcription",
                {
                    "segment_id": segment_id,
                    "silence_duration_ms": (
                        silence_duration_ms
                    ),
                    "forced_finalisation": (
                        forced_finalisation
                    ),
                    "turn_completion_confirmed": (
                        turn_completion_confirmed
                    ),
                    "transcription_backend": (
                        transcription_backend
                    ),
                    "timing": timing,
                    "stream": summary.model_dump(),
                    "transcription": (
                        transcription.model_dump()
                    ),
                },
            )

        async def cancel_moonshine_session(
            session: MoonshineStreamingSession,
        ) -> None:
            """
            Stop a Moonshine stream whose audio segment was abandoned.

            Moonshine stop operations are synchronous, so they run in
            the threadpool rather than blocking the FastAPI event loop.
            """

            try:
                await run_in_threadpool(
                    session.cancel
                )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Moonshine session cancellation failed."
                )
        
                
        async def evaluate_smart_turn_candidate(
            *,
            segment_id: str,
            candidate_id: int,
            pcm_audio: bytes,
            sample_rate: int,
            channels: int,
            silence_duration_ms: int,
            audio_duration_ms: int,
        ) -> None:
            nonlocal last_complete_candidate

            if smart_turn_service is None:
                await send_audio_error(
                    "Smart Turn is not enabled.",
                    segment_id=segment_id,
                    candidate_id=candidate_id,
                )
                return

            try:
                prediction = await run_in_threadpool(
                    smart_turn_service.predict,
                    pcm_audio,
                    sample_rate,
                    channels=channels,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                await send_audio_error(
                    f"Smart Turn prediction failed: {error}",
                    segment_id=segment_id,
                    candidate_id=candidate_id,
                )
                return

            prediction_is_current = (
                active_segment_id == segment_id
                and active_candidate_id == candidate_id
            )
            result = SmartTurnResult(
                completion_probability=(
                    prediction.completion_probability
                ),
                turn_complete=prediction.turn_complete,
                feature_extraction_seconds=(
                    prediction.feature_extraction_seconds
                ),
                inference_seconds=(
                    prediction.inference_seconds
                ),
                total_seconds=prediction.total_seconds,
            )
            log_payload = {
                "candidate_id": candidate_id,
                "segment_id": segment_id,
                "silence_ms": silence_duration_ms,
                "audio_duration_ms": audio_duration_ms,
                "completion_probability": (
                    prediction.completion_probability
                ),
                "turn_complete": prediction.turn_complete,
                "smart_turn_seconds": (
                    prediction.total_seconds
                ),
                "speech_resumed_during_prediction": (
                    not prediction_is_current
                ),
                "forced_finalisation": False,
            }
            logger.info(
                "smart_turn_candidate %s",
                json.dumps(log_payload),
            )

            await send_message(
                "smart_turn_result",
                {
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "silence_duration_ms": (
                        silence_duration_ms
                    ),
                    "audio_duration_ms": audio_duration_ms,
                    "stale": not prediction_is_current,
                    **result.model_dump(),
                },
            )

            if not prediction_is_current:
                return

            if prediction.turn_complete:
                last_complete_candidate = {
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "returned_at": perf_counter(),
                }
                return

            await send_message(
                "awaiting_speech_continuation",
                {
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "completion_probability": (
                        prediction.completion_probability
                    ),
                    "turn_complete": False,
                },
            )

        def start_background_task(
            coroutine: Coroutine[Any, Any, None],
        ) -> None:
            task = asyncio.create_task(coroutine)
            background_tasks.add(task)
            task.add_done_callback(
                background_tasks.discard
            )

        async def finalise_active_segment(
            *,
            silence_duration_ms: int,
            forced_finalisation: bool,
            smart_turn_confirmed_at: float | None,
            finalisation_received_at: float,
        ) -> None:
            nonlocal active_segment_id
            nonlocal active_buffer
            nonlocal active_candidate_id
            nonlocal active_moonshine_session

            if (
                active_buffer is None
                or active_segment_id is None
            ):
                await send_audio_error(
                    "No active audio segment exists.",
                )
                return

            detached_segment_id = active_segment_id
            detached_buffer = active_buffer
            detached_moonshine_session = (
                active_moonshine_session
            )

            active_segment_id = None
            active_buffer = None
            active_candidate_id = None
            active_moonshine_session = None

            if not detached_buffer.total_bytes:
                if (
                    detached_moonshine_session
                    is not None
                ):
                    start_background_task(
                        cancel_moonshine_session(
                            detached_moonshine_session
                        )
                    )

                await send_audio_error(
                    "No audio data was received.",
                    segment_id=detached_segment_id,
                )
                return

            summary = detached_buffer.summary()
            logger.info(
                "audio_segment_finalised %s",
                json.dumps(
                    {
                        "segment_id": detached_segment_id,
                        "silence_ms": silence_duration_ms,
                        "audio_duration_ms": round(
                            summary.duration_seconds * 1_000
                        ),
                        "forced_finalisation": (
                            forced_finalisation
                        ),
                    }
                ),
            )

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
                    "forced_finalisation": (
                        forced_finalisation
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
                    forced_finalisation=(
                        forced_finalisation
                    ),
                    turn_completion_confirmed=(
                        smart_turn_service is not None
                    ),
                    moonshine_session=(
                        detached_moonshine_session
                    ),
                    smart_turn_confirmed_at=(
                        smart_turn_confirmed_at
                    ),
                    finalisation_received_at=(
                        finalisation_received_at
                    ),
                )
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

                    active_buffer.append(
                        binary_chunk
                    )

                    if (
                        active_moonshine_session
                        is not None
                    ):
                        try:
                            active_moonshine_session.add_pcm16(
                                binary_chunk,
                                sample_rate=(
                                    active_buffer.sample_rate
                                ),
                                channels=(
                                    active_buffer.channels
                                ),
                            )

                        except Exception:
                            logger.exception(
                                "Moonshine rejected an audio "
                                "chunk for segment %s. "
                                "The segment will use Whisper.",
                                active_segment_id,
                            )

                            failed_session = (
                                active_moonshine_session
                            )

                            active_moonshine_session = None

                            start_background_task(
                                cancel_moonshine_session(
                                    failed_session
                                )
                            )

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

                    if last_complete_candidate is not None:
                        elapsed_ms = (
                            perf_counter()
                            - last_complete_candidate["returned_at"]
                        ) * 1_000

                        logger.info(
                            "speech_after_smart_turn_complete %s",
                            json.dumps(
                                {
                                    "prior_segment_id": (
                                        last_complete_candidate[
                                            "segment_id"
                                        ]
                                    ),
                                    "prior_candidate_id": (
                                        last_complete_candidate[
                                            "candidate_id"
                                        ]
                                    ),
                                    "resumed_after_ms": round(
                                        elapsed_ms,
                                        3,
                                    ),
                                    "within_250_ms": (
                                        elapsed_ms <= 250
                                    ),
                                    "within_500_ms": (
                                        elapsed_ms <= 500
                                    ),
                                    "within_1000_ms": (
                                        elapsed_ms <= 1_000
                                    ),
                                }
                            ),
                        )

                        last_complete_candidate = None

                    active_segment_id = segment_id
                    active_candidate_id = None

                    active_buffer = AudioStreamBuffer(
                        sample_rate=sample_rate,
                        channels=channels,
                        sample_width_bytes=(
                            PCM16_SAMPLE_WIDTH_BYTES
                        ),
                    )

                    active_moonshine_session = None

                    if active_moonshine_service is not None:
                        try:
                            active_moonshine_session = (
                                await run_in_threadpool(
                                    active_moonshine_service
                                    .create_session
                                )
                            )

                        except Exception:
                            logger.exception(
                                "Could not create Moonshine "
                                "session for segment %s. "
                                "The segment will use Whisper.",
                                segment_id,
                            )

                    known_segment_ids.add(segment_id)

                    await send_message(
                        "audio_segment_started",
                        {
                            "segment_id": segment_id,
                            "sample_rate": sample_rate,
                            "channels": channels,
                            "sample_format": sample_format,
                            "smart_turn_enabled": (
                                smart_turn_service is not None
                            ),
                            "transcription_backend": (
                                "moonshine"
                                if active_moonshine_session
                                is not None
                                else "whisper"
                            ),
                        },
                    )

                elif event_type == "speech_resumed":
                    requested_segment_id = payload.get(
                        "segment_id"
                    )

                    if (
                        active_buffer is None
                        or active_segment_id is None
                    ):
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

                    active_candidate_id = None

                    if (
                        last_complete_candidate
                        is not None
                        and last_complete_candidate[
                            "segment_id"
                        ]
                        == active_segment_id
                    ):
                        last_complete_candidate = None

                elif event_type == "candidate_segment":
                    requested_segment_id = payload.get(
                        "segment_id"
                    )

                    if smart_turn_service is None:
                        await send_audio_error(
                            "Smart Turn is not enabled.",
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

                    try:
                        candidate_id = int(
                            payload.get("candidate_id")
                        )
                        silence_duration_ms = int(
                            payload.get(
                                "silence_duration_ms",
                                0,
                            )
                        )
                    except (TypeError, ValueError):
                        await send_audio_error(
                            (
                                "candidate_id and "
                                "silence_duration_ms must be "
                                "non-negative integers."
                            ),
                            segment_id=active_segment_id,
                        )
                        continue

                    if (
                        candidate_id < 0
                        or silence_duration_ms < 0
                    ):
                        await send_audio_error(
                            (
                                "candidate_id and "
                                "silence_duration_ms must be "
                                "non-negative."
                            ),
                            segment_id=active_segment_id,
                            candidate_id=candidate_id,
                        )
                        continue

                    if not active_buffer.total_bytes:
                        await send_audio_error(
                            "No audio data was received.",
                            segment_id=active_segment_id,
                            candidate_id=candidate_id,
                        )
                        continue

                    active_candidate_id = candidate_id

                    if (
                        last_complete_candidate
                        is not None
                        and last_complete_candidate[
                            "segment_id"
                        ]
                        == active_segment_id
                    ):
                        last_complete_candidate = None

                    candidate_pcm = active_buffer.to_bytes()
                    audio_duration_ms = round(
                        active_buffer.duration_seconds * 1_000
                    )

                    await send_message(
                        "smart_turn_started",
                        {
                            "segment_id": active_segment_id,
                            "candidate_id": candidate_id,
                            "silence_duration_ms": (
                                silence_duration_ms
                            ),
                            "audio_duration_ms": (
                                audio_duration_ms
                            ),
                        },
                    )

                    start_background_task(
                        evaluate_smart_turn_candidate(
                            segment_id=active_segment_id,
                            candidate_id=candidate_id,
                            pcm_audio=candidate_pcm,
                            sample_rate=(
                                active_buffer.sample_rate
                            ),
                            channels=active_buffer.channels,
                            silence_duration_ms=(
                                silence_duration_ms
                            ),
                            audio_duration_ms=(
                                audio_duration_ms
                            ),
                        )
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

                    forced_finalisation = bool(
                        payload.get(
                            "forced_finalisation",
                            False,
                        )
                    )
                    requested_candidate_id = payload.get(
                        "candidate_id"
                    )

                    candidate_was_confirmed = (
                        last_complete_candidate
                        is not None
                        and last_complete_candidate[
                            "segment_id"
                        ]
                        == active_segment_id
                        and last_complete_candidate[
                            "candidate_id"
                        ]
                        == requested_candidate_id
                    )

                    finalisation_received_at = perf_counter()

                    smart_turn_confirmed_at = (
                        last_complete_candidate["returned_at"]
                        if candidate_was_confirmed
                        else None
                    )

                    if (
                        not forced_finalisation
                        and smart_turn_service is not None
                        and (
                            requested_candidate_id
                            != active_candidate_id
                            or not candidate_was_confirmed
                        )
                    ):
                        await send_audio_error(
                            (
                                "The Smart Turn candidate is "
                                "not current and confirmed "
                                "complete."
                            ),
                            segment_id=active_segment_id,
                        )
                        continue

                    await finalise_active_segment(
                        silence_duration_ms=(
                            silence_duration_ms
                        ),
                        forced_finalisation=(
                            forced_finalisation
                        ),
                        smart_turn_confirmed_at=(
                            smart_turn_confirmed_at
                        ),
                        finalisation_received_at=(
                            finalisation_received_at
                        ),
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

                    cancelled_segment_id = (
                        active_segment_id
                    )

                    cancelled_moonshine_session = (
                        active_moonshine_session
                    )

                    active_segment_id = None
                    active_buffer = None
                    active_candidate_id = None
                    active_moonshine_session = None

                    if (
                        cancelled_moonshine_session
                        is not None
                    ):
                        start_background_task(
                            cancel_moonshine_session(
                                cancelled_moonshine_session
                            )
                        )

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
            if active_moonshine_session is not None:
                try:
                    await run_in_threadpool(
                        active_moonshine_session.cancel
                    )

                except Exception:
                    logger.exception(
                        "Could not cancel the active "
                        "Moonshine session during "
                        "WebSocket shutdown."
                    )
            connection_open = False

            for task in background_tasks:
                task.cancel()

            if background_tasks:
                await asyncio.gather(
                    *background_tasks,
                    return_exceptions=True,
                )

    return router
