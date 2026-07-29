from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import wave

import numpy as np
from websockets.asyncio.client import connect


TARGET_SAMPLE_RATE = 16_000
CHUNK_DURATION_MS = 20
VAD_SPEECH_START_MS = 40
VAD_PRE_ROLL_MS = 250
VAD_SPEECH_END_SILENCE_MS = 600


def load_pcm16_mono(
    audio_path: Path,
) -> bytes:
    with wave.open(str(audio_path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw_audio = wav_file.readframes(frame_count)

    if sample_width != 2:
        raise ValueError(
            "The latency fixture must contain 16-bit PCM audio."
        )

    samples = np.frombuffer(
        raw_audio,
        dtype="<i2",
    ).astype(np.float32)

    if channels > 1:
        samples = samples.reshape(
            -1,
            channels,
        ).mean(axis=1)

    if sample_rate != TARGET_SAMPLE_RATE:
        source_positions = np.arange(
            samples.size,
            dtype=np.float64,
        )
        target_size = round(
            samples.size
            * TARGET_SAMPLE_RATE
            / sample_rate
        )
        target_positions = np.linspace(
            0,
            max(samples.size - 1, 0),
            target_size,
        )
        samples = np.interp(
            target_positions,
            source_positions,
            samples,
        )

    return np.clip(
        np.rint(samples),
        -32768,
        32767,
    ).astype("<i2").tobytes()


class Timeline:
    def __init__(self) -> None:
        self.started_at: float | None = None
        self.events: list[dict] = []

    def start(self) -> None:
        self.started_at = perf_counter()
        self.mark("voice_onset")

    def mark(
        self,
        name: str,
        **details,
    ) -> None:
        if self.started_at is None:
            elapsed_seconds = 0.0
        else:
            elapsed_seconds = (
                perf_counter() - self.started_at
            )

        previous_seconds = (
            self.events[-1]["elapsed_seconds"]
            if self.events
            else 0.0
        )
        self.events.append(
            {
                "name": name,
                "elapsed_seconds": round(
                    elapsed_seconds,
                    4,
                ),
                "interval_seconds": round(
                    elapsed_seconds
                    - previous_seconds,
                    4,
                ),
                **details,
            }
        )


async def receive_json(websocket) -> dict:
    message = await websocket.recv()

    if not isinstance(message, str):
        raise RuntimeError(
            "Expected a JSON text WebSocket message."
        )

    return json.loads(message)


async def stream_pcm_at_natural_speed(
    websocket,
    pcm_audio: bytes,
    timeline: Timeline,
) -> None:
    bytes_per_sample = 2
    speech_start_samples = round(
        TARGET_SAMPLE_RATE
        * VAD_SPEECH_START_MS
        / 1000
    )
    speech_start_bytes = (
        speech_start_samples
        * bytes_per_sample
    )
    pre_roll_silence_samples = round(
        TARGET_SAMPLE_RATE
        * (
            VAD_PRE_ROLL_MS
            - VAD_SPEECH_START_MS
        )
        / 1000
    )

    await asyncio.sleep(
        VAD_SPEECH_START_MS / 1000
    )
    timeline.mark(
        "vad_speech_confirmed",
        configured_duration_ms=(
            VAD_SPEECH_START_MS
        ),
    )

    segment_id = f"latency-{uuid4()}"
    await websocket.send(
        json.dumps(
            {
                "type": "start_segment",
                "payload": {
                    "segment_id": segment_id,
                    "sample_rate": (
                        TARGET_SAMPLE_RATE
                    ),
                    "channels": 1,
                    "sample_format": (
                        "pcm_s16le"
                    ),
                },
            }
        )
    )

    started_message = await receive_json(
        websocket
    )
    timeline.mark(
        started_message["type"],
        segment_id=segment_id,
    )

    pre_roll = (
        np.zeros(
            pre_roll_silence_samples,
            dtype="<i2",
        ).tobytes()
        + pcm_audio[:speech_start_bytes]
    )
    await websocket.send(pre_roll)
    timeline.mark(
        "first_pcm_received_by_websocket",
        pre_roll_ms=VAD_PRE_ROLL_MS,
    )

    remaining_audio = pcm_audio[
        speech_start_bytes:
    ]
    chunk_samples = round(
        TARGET_SAMPLE_RATE
        * CHUNK_DURATION_MS
        / 1000
    )
    chunk_bytes = (
        chunk_samples * bytes_per_sample
    )

    speech_stream_started_at = (
        perf_counter()
    )
    speech_bytes_sent = 0

    for offset in range(
        0,
        len(remaining_audio),
        chunk_bytes,
    ):
        chunk = remaining_audio[
            offset:offset + chunk_bytes
        ]
        await websocket.send(chunk)
        speech_bytes_sent += len(chunk)
        target_elapsed_seconds = (
            speech_bytes_sent
            / bytes_per_sample
            / TARGET_SAMPLE_RATE
        )
        remaining_wait_seconds = (
            target_elapsed_seconds
            - (
                perf_counter()
                - speech_stream_started_at
            )
        )

        if remaining_wait_seconds > 0:
            await asyncio.sleep(
                remaining_wait_seconds
            )

    timeline.mark(
        "spoken_audio_complete",
        spoken_audio_seconds=round(
            len(pcm_audio)
            / bytes_per_sample
            / TARGET_SAMPLE_RATE,
            4,
        ),
    )

    silence_chunk = np.zeros(
        chunk_samples,
        dtype="<i2",
    ).tobytes()
    silence_chunk_count = round(
        VAD_SPEECH_END_SILENCE_MS
        / CHUNK_DURATION_MS
    )

    silence_started_at = perf_counter()

    for chunk_index in range(
        silence_chunk_count
    ):
        await websocket.send(
            silence_chunk
        )
        target_elapsed_seconds = (
            (chunk_index + 1)
            * CHUNK_DURATION_MS
            / 1000
        )
        remaining_wait_seconds = (
            target_elapsed_seconds
            - (
                perf_counter()
                - silence_started_at
            )
        )

        if remaining_wait_seconds > 0:
            await asyncio.sleep(
                remaining_wait_seconds
            )

    timeline.mark(
        "vad_silence_threshold_reached",
        configured_duration_ms=(
            VAD_SPEECH_END_SILENCE_MS
        ),
    )

    await websocket.send(
        json.dumps(
            {
                "type": "finalise_segment",
                "payload": {
                    "segment_id": segment_id,
                    "silence_duration_ms": (
                        VAD_SPEECH_END_SILENCE_MS
                    ),
                },
            }
        )
    )
    timeline.mark(
        "audio_segment_finalise_sent",
        segment_id=segment_id,
    )


async def run_trace(
    *,
    audio_path: Path,
    backend_base_url: str,
    output_path: Path,
) -> dict:
    pcm_audio = load_pcm16_mono(
        audio_path
    )
    websocket_base_url = (
        backend_base_url
        .replace("http://", "ws://")
        .replace("https://", "wss://")
        .rstrip("/")
    )
    timeline = Timeline()

    async with connect(
        (
            f"{websocket_base_url}"
            "/api/conversation/turn-buffer/stream"
        ),
        open_timeout=10,
    ) as turn_websocket:
        ready_message = await receive_json(
            turn_websocket
        )
        conversation_id = (
            ready_message["payload"][
                "conversation_id"
            ]
        )

        async with connect(
            (
                f"{websocket_base_url}"
                "/api/audio/stream"
            ),
            open_timeout=10,
        ) as audio_websocket:
            timeline.start()
            await stream_pcm_at_natural_speed(
                audio_websocket,
                pcm_audio,
                timeline,
            )

            transcript = ""
            silence_duration_ms = (
                VAD_SPEECH_END_SILENCE_MS
            )

            while True:
                audio_message = (
                    await asyncio.wait_for(
                        receive_json(
                            audio_websocket
                        ),
                        timeout=120,
                    )
                )
                message_type = (
                    audio_message["type"]
                )
                payload = (
                    audio_message.get(
                        "payload",
                        {},
                    )
                )
                timeline.mark(
                    message_type,
                    payload=payload,
                )

                if (
                    message_type
                    == "audio_error"
                ):
                    raise RuntimeError(
                        payload.get(
                            "detail",
                            "Audio stream error.",
                        )
                    )

                if (
                    message_type
                    == "audio_transcription"
                ):
                    transcript = (
                        payload[
                            "transcription"
                        ]["text"]
                    )
                    silence_duration_ms = (
                        payload.get(
                            "silence_duration_ms",
                            silence_duration_ms,
                        )
                    )
                    break

        request_id = str(uuid4())
        await turn_websocket.send(
            json.dumps(
                {
                    "type": "turn_event",
                    "request_id": request_id,
                    "payload": {
                        "partial_utterance": (
                            transcript
                        ),
                        "is_speech_active": False,
                        "silence_duration_ms": (
                            silence_duration_ms
                        ),
                        "assistant_was_speaking": (
                            False
                        ),
                        "debug": True,
                    },
                }
            )
        )
        timeline.mark(
            "turn_event_sent",
            request_id=request_id,
            transcript=transcript,
        )

        query_result = None

        while True:
            turn_message = (
                await asyncio.wait_for(
                    receive_json(
                        turn_websocket
                    ),
                    timeout=180,
                )
            )
            message_type = turn_message["type"]
            payload = turn_message.get(
                "payload",
                {},
            )
            details = {
                "request_id": (
                    turn_message.get(
                        "request_id"
                    )
                ),
            }

            if message_type == "response_delta":
                details["text"] = payload.get(
                    "text",
                    "",
                )
            else:
                details["payload"] = payload

            timeline.mark(
                message_type,
                **details,
            )

            if message_type == "turn_error":
                raise RuntimeError(
                    payload.get(
                        "detail",
                        "Turn stream error.",
                    )
                )

            if message_type == "query_complete":
                query_result = payload
                break

    report = {
        "fixture": str(audio_path),
        "conversation_id": conversation_id,
        "request_id": request_id,
        "transcript": transcript,
        "events": timeline.events,
        "query_debug": (
            (
                query_result.get("debug")
                or {}
            ).get("debug_payload")
            if query_result
            else None
        ),
    }
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audio",
        type=Path,
        default=Path(
            "tmp/latency/voice_request.wav"
        ),
    )
    parser.add_argument(
        "--backend",
        default="http://localhost:8000",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "tmp/latency/latest_voice_trace.json"
        ),
    )
    arguments = parser.parse_args()

    report = asyncio.run(
        run_trace(
            audio_path=arguments.audio,
            backend_base_url=(
                arguments.backend
            ),
            output_path=arguments.output,
        )
    )

    print(
        json.dumps(
            report,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
