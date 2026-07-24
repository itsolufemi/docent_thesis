import json

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from conversation_core.services.audio_stream_service import (
    AudioStreamBuffer,
)


DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
PCM16_SAMPLE_WIDTH_BYTES = 2

MAX_STREAM_BYTES = 30 * 1024 * 1024


router = APIRouter()


async def send_audio_error(
    websocket: WebSocket,
    detail: str,
) -> None:
    await websocket.send_json(
        {
            "type": "audio_error",
            "payload": {
                "detail": detail,
            },
        }
    )


@router.websocket("/api/audio/stream")
async def stream_audio(
    websocket: WebSocket,
) -> None:
    await websocket.accept()

    audio_buffer: AudioStreamBuffer | None = None

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            binary_chunk = message.get("bytes")

            if binary_chunk is not None:
                if audio_buffer is None:
                    await send_audio_error(
                        websocket,
                        "Audio stream has not been started.",
                    )
                    continue

                if (
                    audio_buffer.total_bytes
                    + len(binary_chunk)
                    > MAX_STREAM_BYTES
                ):
                    await send_audio_error(
                        websocket,
                        (
                            "Audio stream exceeded the maximum "
                            "permitted size."
                        ),
                    )
                    await websocket.close(
                        code=1009,
                        reason="Audio stream too large.",
                    )
                    return

                audio_buffer.append(binary_chunk)
                continue

            text_message = message.get("text")

            if text_message is None:
                continue

            try:
                event = json.loads(text_message)
            except json.JSONDecodeError:
                await send_audio_error(
                    websocket,
                    "Invalid JSON control message.",
                )
                continue

            event_type = event.get("type")
            payload = event.get("payload") or {}

            if event_type == "start_audio":
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
                        websocket,
                        (
                            "Sample rate and channels must be "
                            "positive integers."
                        ),
                    )
                    continue

                sample_format = payload.get(
                    "sample_format",
                    "pcm_s16le",
                )

                if sample_format != "pcm_s16le":
                    await send_audio_error(
                        websocket,
                        "Only pcm_s16le is supported.",
                    )
                    continue

                if sample_rate <= 0 or channels <= 0:
                    await send_audio_error(
                        websocket,
                        (
                            "Sample rate and channels must be "
                            "positive."
                        ),
                    )
                    continue

                audio_buffer = AudioStreamBuffer(
                    sample_rate=sample_rate,
                    channels=channels,
                    sample_width_bytes=PCM16_SAMPLE_WIDTH_BYTES,
                )

                await websocket.send_json(
                    {
                        "type": "audio_stream_started",
                        "payload": {
                            "sample_rate": sample_rate,
                            "channels": channels,
                            "sample_format": sample_format,
                        },
                    }
                )

            elif event_type == "stop_audio":
                if audio_buffer is None:
                    await send_audio_error(
                        websocket,
                        "No active audio stream exists.",
                    )
                    continue

                summary = audio_buffer.summary()

                await websocket.send_json(
                    {
                        "type": "audio_stream_complete",
                        "payload": summary.model_dump(),
                    }
                )

                audio_buffer = None

            elif event_type == "cancel_audio":
                audio_buffer = None

                await websocket.send_json(
                    {
                        "type": "audio_stream_cancelled",
                        "payload": {},
                    }
                )

            else:
                await send_audio_error(
                    websocket,
                    f"Unknown audio event: {event_type}",
                )

    except WebSocketDisconnect:
        return
