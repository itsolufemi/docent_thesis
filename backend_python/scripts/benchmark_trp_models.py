from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from time import perf_counter

import httpx
import numpy as np


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from config import settings  # noqa: E402
from conversation_core.services.transcription_service import (  # noqa: E402
    default_transcription_service,
)
from conversation_core.services.trp_service import (  # noqa: E402
    build_trp_prompt,
    parse_trp_prediction_json,
    predict_transition_relevance,
)
from conversation_core.schemas.trp_schemas import (  # noqa: E402
    TRPPrediction,
)
from scripts.measure_voice_pipeline import (  # noqa: E402
    TARGET_SAMPLE_RATE,
    VAD_PRE_ROLL_MS,
    VAD_SPEECH_START_MS,
    VAD_SPEECH_END_SILENCE_MS,
    load_pcm16_mono,
)


DEFAULT_MODELS = [
    "gemini-3-flash-preview:latest",
    "gpt-oss:20b-cloud",
    "gemma4:cloud",
    "gemma4:31b-cloud",
    "qwen3.5:cloud",
]


def build_stream_segment(
    audio_path: Path,
) -> tuple[bytes, float]:
    pcm_audio = load_pcm16_mono(audio_path)
    sample_width_bytes = 2
    pre_roll_silence_ms = (
        VAD_PRE_ROLL_MS
        - VAD_SPEECH_START_MS
    )
    pre_roll_samples = round(
        TARGET_SAMPLE_RATE
        * pre_roll_silence_ms
        / 1000
    )
    trailing_silence_samples = round(
        TARGET_SAMPLE_RATE
        * VAD_SPEECH_END_SILENCE_MS
        / 1000
    )
    stream_pcm = (
        np.zeros(
            pre_roll_samples,
            dtype="<i2",
        ).tobytes()
        + pcm_audio
        + np.zeros(
            trailing_silence_samples,
            dtype="<i2",
        ).tobytes()
    )
    spoken_audio_seconds = (
        len(pcm_audio)
        / sample_width_bytes
        / TARGET_SAMPLE_RATE
    )
    return stream_pcm, spoken_audio_seconds


def measure_transcription(
    stream_pcm: bytes,
    *,
    runs: int,
) -> tuple[str, list[float]]:
    # Load and warm Whisper before the recorded passes.
    default_transcription_service.transcribe_pcm16(
        stream_pcm,
        sample_rate=TARGET_SAMPLE_RATE,
        channels=1,
    )

    transcript = ""
    timings: list[float] = []

    for run_index in range(runs):
        started_at = perf_counter()
        result = (
            default_transcription_service
            .transcribe_pcm16(
                stream_pcm,
                sample_rate=(
                    TARGET_SAMPLE_RATE
                ),
                channels=1,
            )
        )
        elapsed_seconds = (
            perf_counter() - started_at
        )
        transcript = result.text
        timings.append(elapsed_seconds)
        print(
            "Whisper "
            f"{run_index + 1}/{runs}: "
            f"{elapsed_seconds:.4f}s "
            f"-> {transcript!r}",
            flush=True,
        )

    return transcript, timings


def call_trp_model(
    *,
    model: str,
    transcript: str,
) -> dict:
    previous_model = (
        settings.ollama_trp_model
    )
    settings.ollama_trp_model = model
    started_at = perf_counter()

    try:
        prediction = (
            predict_transition_relevance(
                partial_utterance=transcript,
                previous_turns=[],
            )
        )
        elapsed_seconds = (
            perf_counter() - started_at
        )
        return {
            "success": True,
            "elapsed_seconds": round(
                elapsed_seconds,
                4,
            ),
            "service_prediction_seconds": (
                prediction
                .prediction_seconds
            ),
            "trp_probability": (
                prediction
                .trp_probability
            ),
            "turn_complete": (
                prediction.turn_complete
            ),
            "reason": prediction.reason,
        }
    except Exception as error:
        return {
            "success": False,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": (
                type(error).__name__
            ),
            "error": str(error),
        }
    finally:
        settings.ollama_trp_model = (
            previous_model
        )


def call_structured_trp_model(
    *,
    model: str,
    transcript: str,
    previous_turns: list[str] | None = None,
) -> dict:
    started_at = perf_counter()
    prompt = build_trp_prompt(
        partial_utterance=transcript,
        previous_turns=(
            previous_turns or []
        ),
    )
    think_value: bool | str = False

    if model.startswith("gpt-oss:"):
        think_value = "low"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think_value,
        "format": {
            "type": "object",
            "properties": {
                "trp_probability": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "turn_complete": {
                    "type": "boolean",
                },
                "reason": {
                    "type": "string",
                },
            },
            "required": [
                "trp_probability",
                "turn_complete",
                "reason",
            ],
        },
        "options": {
            "temperature": 0,
            "num_predict": 160,
        },
    }

    try:
        response = httpx.post(
            (
                f"{settings.ollama_base_url}"
                "/api/generate"
            ),
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        response_payload = response.json()
        raw_response = (
            response_payload.get(
                "response",
                "",
            ).strip()
        )

        if not raw_response:
            raise ValueError(
                "Ollama returned no answer content "
                f"(done_reason="
                f"{response_payload.get('done_reason')}, "
                f"thinking_characters="
                f"{len(response_payload.get('thinking', ''))})."
            )

        prediction = TRPPrediction.model_validate(
            parse_trp_prediction_json(
                raw_response
            )
        )
        model_turn_complete = (
            prediction.turn_complete
        )
        prediction.turn_complete = (
            prediction.trp_probability
            >= 0.70
        )
        elapsed_seconds = (
            perf_counter() - started_at
        )
        return {
            "success": True,
            "elapsed_seconds": round(
                elapsed_seconds,
                4,
            ),
            "trp_probability": (
                prediction
                .trp_probability
            ),
            "turn_complete": (
                prediction.turn_complete
            ),
            "model_turn_complete": (
                model_turn_complete
            ),
            "reason": prediction.reason,
            "think": think_value,
            "ollama_total_seconds": round(
                (
                    response_payload.get(
                        "total_duration",
                        0,
                    )
                    / 1_000_000_000
                ),
                4,
            ),
            "prompt_eval_count": (
                response_payload.get(
                    "prompt_eval_count"
                )
            ),
            "eval_count": (
                response_payload.get(
                    "eval_count"
                )
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": (
                type(error).__name__
            ),
            "error": str(error),
            "think": think_value,
        }


def summarise_model(
    *,
    model: str,
    samples: list[dict],
    pre_trp_seconds: float,
) -> dict:
    valid_samples = [
        sample
        for sample in samples
        if sample["success"]
    ]
    valid_times = [
        sample["elapsed_seconds"]
        for sample in valid_samples
    ]
    expected_decisions = [
        sample
        for sample in valid_samples
        if sample["turn_complete"] is True
    ]

    summary = {
        "model": model,
        "runs": len(samples),
        "successful_runs": len(
            valid_samples
        ),
        "expected_decision_runs": len(
            expected_decisions
        ),
        "samples": samples,
    }

    if not valid_times:
        return summary

    median_seconds = statistics.median(
        valid_times
    )
    summary.update(
        {
            "median_trp_seconds": round(
                median_seconds,
                4,
            ),
            "mean_trp_seconds": round(
                statistics.mean(
                    valid_times
                ),
                4,
            ),
            "minimum_trp_seconds": min(
                valid_times
            ),
            "maximum_trp_seconds": max(
                valid_times
            ),
            "population_stddev_seconds": (
                round(
                    statistics.pstdev(
                        valid_times
                    ),
                    4,
                )
            ),
            "median_voice_to_classifier_seconds": (
                round(
                    pre_trp_seconds
                    + median_seconds,
                    4,
                )
            ),
        }
    )
    return summary


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
        "--runs",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--transcription-runs",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "tmp/latency/"
            "trp_model_benchmark.json"
        ),
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
    )
    parser.add_argument(
        "--request-profile",
        choices=[
            "current",
            "structured",
        ],
        default="current",
    )
    arguments = parser.parse_args()

    if arguments.runs < 1:
        raise ValueError(
            "--runs must be at least 1."
        )

    stream_pcm, spoken_audio_seconds = (
        build_stream_segment(
            arguments.audio
        )
    )
    transcript, transcription_times = (
        measure_transcription(
            stream_pcm,
            runs=(
                arguments
                .transcription_runs
            ),
        )
    )
    median_transcription_seconds = (
        statistics.median(
            transcription_times
        )
    )
    pre_trp_seconds = (
        spoken_audio_seconds
        + (
            VAD_SPEECH_END_SILENCE_MS
            / 1000
        )
        + median_transcription_seconds
    )

    print(
        "\nWarming each TRP model once...",
        flush=True,
    )

    warmups = {}
    trp_caller = (
        call_trp_model
        if (
            arguments.request_profile
            == "current"
        )
        else call_structured_trp_model
    )

    for model in arguments.models:
        warmup = trp_caller(
            model=model,
            transcript=transcript,
        )
        warmups[model] = warmup
        print(
            f"{model}: "
            f"{warmup['elapsed_seconds']:.4f}s "
            f"success={warmup['success']}",
            flush=True,
        )

    samples_by_model = {
        model: []
        for model in arguments.models
    }
    random_generator = random.Random(
        20260729
    )

    for run_index in range(
        arguments.runs
    ):
        model_order = list(
            arguments.models
        )
        random_generator.shuffle(
            model_order
        )
        print(
            f"\nMeasured round "
            f"{run_index + 1}/"
            f"{arguments.runs}",
            flush=True,
        )

        for model in model_order:
            sample = trp_caller(
                model=model,
                transcript=transcript,
            )
            samples_by_model[model].append(
                sample
            )
            print(
                f"{model}: "
                f"{sample['elapsed_seconds']:.4f}s "
                f"success={sample['success']} "
                f"complete="
                f"{sample.get('turn_complete')}",
                flush=True,
            )

    summaries = [
        summarise_model(
            model=model,
            samples=(
                samples_by_model[model]
            ),
            pre_trp_seconds=(
                pre_trp_seconds
            ),
        )
        for model in arguments.models
    ]
    ranked_models = sorted(
        summaries,
        key=lambda summary: (
            (
                summary["successful_runs"]
                != arguments.runs
            ),
            (
                summary.get(
                    "median_trp_seconds",
                    float("inf"),
                )
            ),
        ),
    )

    report = {
        "fixture": str(
            arguments.audio
        ),
        "request_profile": (
            arguments.request_profile
        ),
        "transcript": transcript,
        "spoken_audio_seconds": round(
            spoken_audio_seconds,
            4,
        ),
        "vad_finalisation_seconds": (
            VAD_SPEECH_END_SILENCE_MS
            / 1000
        ),
        "transcription_timings_seconds": [
            round(value, 4)
            for value in transcription_times
        ],
        "median_transcription_seconds": (
            round(
                median_transcription_seconds,
                4,
            )
        ),
        "median_pre_trp_seconds": round(
            pre_trp_seconds,
            4,
        ),
        "warmups": warmups,
        "models": summaries,
        "ranking": [
            summary["model"]
            for summary in ranked_models
        ],
    }
    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    arguments.output.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nRanking:", flush=True)

    for rank, summary in enumerate(
        ranked_models,
        start=1,
    ):
        print(
            f"{rank}. {summary['model']}: "
            f"median="
            f"{summary.get('median_trp_seconds')}s "
            f"successful="
            f"{summary['successful_runs']}/"
            f"{summary['runs']}",
            flush=True,
        )

    print(
        f"\nFull report: {arguments.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
