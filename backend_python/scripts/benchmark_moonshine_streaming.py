"""
Benchmark Moonshine using a WAV file fed in small chunks.

This simulates the way the browser sends PCM audio to the backend.
It measures:

1. Model-loading time.
2. Time until the first partial transcript.
3. Time from the end of audio input until the final transcript.
4. The final recognised text.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

from moonshine_voice import (
    Transcriber,
    TranscriptEventListener,
    get_model_for_language,
    load_wav_file,
)


@dataclass
class BenchmarkTimings:
    audio_started_at: float | None = None
    audio_finished_at: float | None = None
    first_partial_at: float | None = None
    final_transcript_at: float | None = None


class BenchmarkListener(TranscriptEventListener):
    def __init__(self, timings: BenchmarkTimings) -> None:
        super().__init__()
        self.timings = timings
        self.completed_lines: list[str] = []

    def on_line_started(self, event) -> None:
        text = event.line.text.strip()

        print(
            f"[line started] "
            f"{event.line.start_time:.2f}s: {text}"
        )

    def on_line_text_changed(self, event) -> None:
        text = event.line.text.strip()

        if not text:
            return

        if self.timings.first_partial_at is None:
            self.timings.first_partial_at = (
                time.perf_counter()
            )

        print(
            f"[partial] "
            f"{event.line.start_time:.2f}s: {text}"
        )

    def on_line_completed(self, event) -> None:
        text = event.line.text.strip()

        if text:
            self.completed_lines.append(text)

        self.timings.final_transcript_at = (
            time.perf_counter()
        )

        print(
            f"[completed] "
            f"{event.line.start_time:.2f}s: {text}"
        )

    @property
    def final_text(self) -> str:
        return " ".join(self.completed_lines).strip()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Feed WAV audio to Moonshine as a simulated "
            "real-time PCM stream."
        )
    )

    parser.add_argument(
        "audio_path",
        type=Path,
        help="Path to a mono or stereo WAV recording.",
    )

    parser.add_argument(
        "--language",
        default="en",
        help="Moonshine language code.",
    )

    parser.add_argument(
        "--model-arch",
        type=int,
        default=None,
        help=(
            "Optional Moonshine model architecture. "
            "Leave unset to use the default model."
        ),
    )

    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=20,
        help=(
            "Duration of each simulated incoming audio "
            "chunk in milliseconds."
        ),
    )

    parser.add_argument(
        "--no-realtime",
        action="store_true",
        help=(
            "Feed chunks as quickly as possible instead "
            "of waiting for their real-time duration."
        ),
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    audio_path = arguments.audio_path.resolve()

    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file was not found: {audio_path}"
        )

    model_load_started_at = time.perf_counter()

    model_path, model_arch = get_model_for_language(
        arguments.language,
        arguments.model_arch,
    )

    transcriber = Transcriber(
        model_path=model_path,
        model_arch=model_arch,
        update_interval=0.2,
    )

    model_load_seconds = (
        time.perf_counter() - model_load_started_at
    )

    audio_data, sample_rate = load_wav_file(
        str(audio_path)
    )

    timings = BenchmarkTimings()
    listener = BenchmarkListener(timings)

    transcriber.remove_all_listeners()
    transcriber.add_listener(listener)

    chunk_size = max(
        1,
        int(
            sample_rate
            * arguments.chunk_ms
            / 1_000
        ),
    )

    print()
    print(f"Model path: {model_path}")
    print(f"Model architecture: {model_arch}")
    print(f"Model loading: {model_load_seconds:.4f}s")
    print(f"Audio sample rate: {sample_rate} Hz")
    print(f"Chunk duration: {arguments.chunk_ms} ms")
    print()

    transcriber.start()

    timings.audio_started_at = time.perf_counter()

    for offset in range(
        0,
        len(audio_data),
        chunk_size,
    ):
        chunk = audio_data[
            offset : offset + chunk_size
        ]

        transcriber.add_audio(
            chunk,
            sample_rate,
        )

        if not arguments.no_realtime:
            time.sleep(
                len(chunk) / sample_rate
            )

    timings.audio_finished_at = time.perf_counter()

    stop_called_at = time.perf_counter()

    # stop() forces any still-active transcript line to complete.
    transcriber.stop()

    stop_returned_at = time.perf_counter()

    print()
    print("RESULT")
    print("------")
    print(f"Transcript: {listener.final_text!r}")

    if (
        timings.audio_started_at is not None
        and timings.first_partial_at is not None
    ):
        first_partial_seconds = (
            timings.first_partial_at
            - timings.audio_started_at
        )

        print(
            "First partial from audio start: "
            f"{first_partial_seconds:.4f}s"
        )
    else:
        print("First partial from audio start: unavailable")

    if (
    timings.audio_finished_at is not None
    and timings.final_transcript_at is not None
    ):
        completion_offset_seconds = (
            timings.final_transcript_at
            - timings.audio_finished_at
        )

        if completion_offset_seconds < 0:
            print(
                "Transcript completed before WAV input ended: "
                f"{abs(completion_offset_seconds):.4f}s"
            )
        else:
            print(
                "Transcript completed after WAV input ended: "
                f"{completion_offset_seconds:.4f}s"
            )
    else:
        print("Transcript completion timing: unavailable")

    print(
        "Moonshine stop/finalisation call: "
        f"{stop_returned_at - stop_called_at:.4f}s"
    )

if __name__ == "__main__":
    main()