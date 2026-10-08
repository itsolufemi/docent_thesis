from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from transformers import WhisperFeatureExtractor


WORKSPACE_ROOT = Path(__file__).resolve().parent
MODEL_REPOSITORY = "pipecat-ai/smart-turn-v3"
MODEL_FILENAMES = {
    "cpu": "smart-turn-v3.2-cpu.onnx",
    "gpu": "smart-turn-v3.2-gpu.onnx",
}
SAMPLE_RATE = 16_000
MAX_AUDIO_SECONDS = 8
COMPLETION_THRESHOLD = 0.5


@dataclass(frozen=True)
class AudioCase:
    case_id: str
    audio_path: Path
    expected_label: str
    transcript: str
    category: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Smart Turn v3.2 on a labelled WAV manifest."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=WORKSPACE_ROOT / "audio_manifest.csv",
    )
    parser.add_argument(
        "--model",
        choices=("auto", "cpu", "gpu"),
        default="auto",
    )
    parser.add_argument("--warmup-runs", type=int, default=5)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=WORKSPACE_ROOT / "results" / "smart_turn_results.json",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> list[AudioCase]:
    cases: list[AudioCase] = []

    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            audio_path = Path(row["audio_path"])
            if not audio_path.is_absolute():
                audio_path = (path.parent / audio_path).resolve()

            expected_label = row["expected_label"].strip().lower()
            if expected_label not in {"complete", "incomplete"}:
                raise ValueError(
                    f"Unsupported expected label {expected_label!r} "
                    f"for {row['case_id']!r}."
                )

            if not audio_path.is_file():
                raise FileNotFoundError(
                    f"Audio file does not exist: {audio_path}"
                )

            cases.append(
                AudioCase(
                    case_id=row["case_id"].strip(),
                    audio_path=audio_path,
                    expected_label=expected_label,
                    transcript=row.get("transcript", "").strip(),
                    category=row.get("category", "").strip(),
                )
            )

    if not cases:
        raise ValueError(f"No audio cases were found in {path}.")

    return cases


def select_model(requested_model: str) -> tuple[str, list[str]]:
    available_providers = ort.get_available_providers()

    if requested_model == "auto":
        requested_model = (
            "gpu"
            if "CUDAExecutionProvider" in available_providers
            else "cpu"
        )

    if (
        requested_model == "gpu"
        and "CUDAExecutionProvider" not in available_providers
    ):
        raise RuntimeError(
            "GPU benchmarking was requested, but ONNX Runtime does not "
            "expose CUDAExecutionProvider. Install onnxruntime-gpu in the "
            "active Jupyter kernel and restart it before rerunning."
        )

    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if requested_model == "gpu"
        else ["CPUExecutionProvider"]
    )
    return requested_model, providers


def prepare_audio(audio_path: Path) -> tuple[np.ndarray, float]:
    started_at = time.perf_counter()
    audio, _ = librosa.load(
        audio_path,
        sr=SAMPLE_RATE,
        mono=True,
    )
    audio = np.asarray(audio, dtype=np.float32)

    max_samples = SAMPLE_RATE * MAX_AUDIO_SECONDS
    if audio.size > max_samples:
        audio = audio[-max_samples:]
    elif audio.size < max_samples:
        audio = np.pad(
            audio,
            (max_samples - audio.size, 0),
            mode="constant",
        )

    return audio, (time.perf_counter() - started_at) * 1_000


def extract_features(
    feature_extractor: WhisperFeatureExtractor,
    audio: np.ndarray,
) -> np.ndarray:
    inputs = feature_extractor(
        audio,
        sampling_rate=SAMPLE_RATE,
        return_tensors="np",
        padding="max_length",
        max_length=MAX_AUDIO_SECONDS * SAMPLE_RATE,
        truncation=True,
        do_normalize=True,
    )
    features = inputs.input_features.squeeze(0).astype(np.float32)
    return np.expand_dims(features, axis=0)


def summarise(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = max(0, int(np.ceil(len(ordered) * 0.95)) - 1)
    return {
        "minimum_ms": round(min(ordered), 3),
        "median_ms": round(statistics.median(ordered), 3),
        "mean_ms": round(statistics.fmean(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "maximum_ms": round(max(ordered), 3),
    }


def run_prediction(
    *,
    session: ort.InferenceSession,
    feature_extractor: WhisperFeatureExtractor,
    audio_path: Path,
) -> tuple[float, dict[str, float]]:
    total_started_at = time.perf_counter()

    audio, audio_load_ms = prepare_audio(audio_path)

    feature_started_at = time.perf_counter()
    input_features = extract_features(feature_extractor, audio)
    feature_extraction_ms = (
        time.perf_counter() - feature_started_at
    ) * 1_000

    inference_started_at = time.perf_counter()
    outputs = session.run(
        None,
        {"input_features": input_features},
    )
    inference_ms = (
        time.perf_counter() - inference_started_at
    ) * 1_000

    probability = float(np.asarray(outputs[0]).squeeze())
    return probability, {
        "audio_load_ms": audio_load_ms,
        "feature_extraction_ms": feature_extraction_ms,
        "inference_ms": inference_ms,
        "end_to_end_ms": (
            time.perf_counter() - total_started_at
        )
        * 1_000,
    }


def benchmark_case(
    *,
    case: AudioCase,
    session: ort.InferenceSession,
    feature_extractor: WhisperFeatureExtractor,
    warmup_runs: int,
    runs: int,
) -> dict[str, Any]:
    for _ in range(warmup_runs):
        run_prediction(
            session=session,
            feature_extractor=feature_extractor,
            audio_path=case.audio_path,
        )

    timings = {
        "audio_load_ms": [],
        "feature_extraction_ms": [],
        "inference_ms": [],
        "end_to_end_ms": [],
    }
    probabilities: list[float] = []

    for _ in range(runs):
        probability, run_timings = run_prediction(
            session=session,
            feature_extractor=feature_extractor,
            audio_path=case.audio_path,
        )
        probabilities.append(probability)

        for timing_name, duration_ms in run_timings.items():
            timings[timing_name].append(duration_ms)

    median_probability = statistics.median(probabilities)
    decision = (
        "complete"
        if median_probability > COMPLETION_THRESHOLD
        else "incomplete"
    )

    return {
        **asdict(case),
        "audio_path": str(case.audio_path),
        "decision": decision,
        "probability_complete": round(median_probability, 6),
        "correct": decision == case.expected_label,
        "runs": runs,
        "timings": {
            name: summarise(values)
            for name, values in timings.items()
        },
        "inference_samples_ms": [
            round(value, 3)
            for value in timings["inference_ms"]
        ],
    }


def main() -> None:
    arguments = parse_arguments()
    if arguments.runs < 1 or arguments.warmup_runs < 0:
        raise ValueError(
            "runs must be at least 1 and warmup-runs cannot be negative."
        )

    cases = load_manifest(arguments.manifest.resolve())
    selected_model, providers = select_model(arguments.model)
    model_filename = MODEL_FILENAMES[selected_model]

    download_started_at = time.perf_counter()
    model_path = Path(
        hf_hub_download(
            repo_id=MODEL_REPOSITORY,
            filename=model_filename,
        )
    )
    model_resolution_ms = (
        time.perf_counter() - download_started_at
    ) * 1_000

    session_options = ort.SessionOptions()
    session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session_options.inter_op_num_threads = 1
    session_options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    )

    session_started_at = time.perf_counter()
    session = ort.InferenceSession(
        str(model_path),
        sess_options=session_options,
        providers=providers,
    )
    session_initialisation_ms = (
        time.perf_counter() - session_started_at
    ) * 1_000

    feature_extractor = WhisperFeatureExtractor(
        chunk_length=MAX_AUDIO_SECONDS
    )

    case_results = [
        benchmark_case(
            case=case,
            session=session,
            feature_extractor=feature_extractor,
            warmup_runs=arguments.warmup_runs,
            runs=arguments.runs,
        )
        for case in cases
    ]

    correct_count = sum(
        result["correct"]
        for result in case_results
    )
    result_payload = {
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "onnxruntime": ort.__version__,
            "available_providers": ort.get_available_providers(),
            "active_providers": session.get_providers(),
        },
        "model": {
            "repository": MODEL_REPOSITORY,
            "filename": model_filename,
            "path": str(model_path),
            "model_resolution_ms": round(model_resolution_ms, 3),
            "session_initialisation_ms": round(
                session_initialisation_ms,
                3,
            ),
        },
        "configuration": {
            "sample_rate": SAMPLE_RATE,
            "max_audio_seconds": MAX_AUDIO_SECONDS,
            "completion_threshold": COMPLETION_THRESHOLD,
            "warmup_runs": arguments.warmup_runs,
            "measured_runs": arguments.runs,
        },
        "summary": {
            "case_count": len(case_results),
            "correct_count": correct_count,
            "accuracy": round(
                correct_count / len(case_results),
                4,
            ),
            "premature_finalisations": sum(
                result["decision"] == "complete"
                and result["expected_label"] == "incomplete"
                for result in case_results
            ),
        },
        "cases": case_results,
    }

    output_path = arguments.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result_payload, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "model": model_filename,
                "active_providers": session.get_providers(),
                "summary": result_payload["summary"],
                "cases": [
                    {
                        "case_id": result["case_id"],
                        "expected": result["expected_label"],
                        "decision": result["decision"],
                        "probability_complete": (
                            result["probability_complete"]
                        ),
                        "median_inference_ms": (
                            result["timings"]["inference_ms"]["median_ms"]
                        ),
                        "median_end_to_end_ms": (
                            result["timings"]["end_to_end_ms"]["median_ms"]
                        ),
                    }
                    for result in case_results
                ],
                "output": str(output_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
