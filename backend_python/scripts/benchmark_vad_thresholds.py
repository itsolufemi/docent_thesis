from __future__ import annotations

import argparse
import io
import json
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    create_conversation,
)
from conversation_core.schemas.turn_buffer_schemas import (  # noqa: E402
    TurnBufferEvent,
)
from conversation_core.services.google_tts_service import (  # noqa: E402
    google_tts_service,
)
from conversation_core.services.transcription_service import (  # noqa: E402
    default_transcription_service,
)
from conversation_core.services.trp_service import (  # noqa: E402
    predict_transition_relevance,
)
from conversation_core.services.turn_buffer_service import (  # noqa: E402
    process_turn_event,
)


TARGET_SAMPLE_RATE = 16_000
WORKLET_FRAME_SAMPLES = 128
SPEECH_THRESHOLD = 0.02
SPEECH_START_DURATION_MS = 40
PRE_ROLL_DURATION_MS = 250
FINAL_TRAILING_SILENCE_MS = 700
THRESHOLDS_MS = [
    200,
    300,
    400,
    450,
    500,
    600,
]


@dataclass(frozen=True)
class FixtureDefinition:
    fixture_id: str
    parts: list[str]
    pauses_ms: list[int]
    first_part_expected_complete: bool | None = None

    @property
    def expected_transcript(self) -> str:
        return " ".join(self.parts)


FIXTURES = [
    FixtureDefinition(
        fixture_id="complete_request",
        parts=[
            "Tell me about The Arab Tent.",
        ],
        pauses_ms=[],
    ),
    FixtureDefinition(
        fixture_id="incomplete_pause_250",
        parts=[
            "Could you tell me about",
            "The Arab Tent?",
        ],
        pauses_ms=[250],
        first_part_expected_complete=False,
    ),
    FixtureDefinition(
        fixture_id="incomplete_pause_350",
        parts=[
            "Could you tell me about",
            "The Arab Tent?",
        ],
        pauses_ms=[350],
        first_part_expected_complete=False,
    ),
    FixtureDefinition(
        fixture_id="incomplete_pause_450",
        parts=[
            "Could you tell me about",
            "The Arab Tent?",
        ],
        pauses_ms=[450],
        first_part_expected_complete=False,
    ),
    FixtureDefinition(
        fixture_id="unfinished_clause_pause_350",
        parts=[
            "I think that",
            "the painting is beautiful.",
        ],
        pauses_ms=[350],
        first_part_expected_complete=False,
    ),
    FixtureDefinition(
        fixture_id="complete_clause_pause_350",
        parts=[
            "The Arab Tent is remarkable.",
            "Its interior is richly decorated.",
        ],
        pauses_ms=[350],
        first_part_expected_complete=True,
    ),
]


def safe_name(text: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        text.lower(),
    ).strip("_")


def decode_google_wav(
    wav_bytes: bytes,
) -> np.ndarray:
    with wave.open(
        io.BytesIO(wav_bytes),
        "rb",
    ) as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw_audio = wav_file.readframes(
            frame_count
        )

    if sample_width != 2:
        raise ValueError(
            "The Google fixture must use PCM16 audio."
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
    ).astype("<i2")


def trim_outer_silence(
    samples: np.ndarray,
    *,
    amplitude_threshold: int = 180,
    padding_ms: int = 40,
) -> np.ndarray:
    active_indices = np.flatnonzero(
        np.abs(
            samples.astype(np.int32)
        )
        >= amplitude_threshold
    )

    if active_indices.size == 0:
        raise ValueError(
            "Synthesised fixture contains no audible samples."
        )

    padding_samples = round(
        TARGET_SAMPLE_RATE
        * padding_ms
        / 1000
    )
    start_index = max(
        0,
        int(active_indices[0])
        - padding_samples,
    )
    end_index = min(
        samples.size,
        int(active_indices[-1])
        + padding_samples
        + 1,
    )
    return samples[
        start_index:end_index
    ]


def load_or_synthesise_part(
    text: str,
    fixture_directory: Path,
) -> np.ndarray:
    output_path = (
        fixture_directory
        / "parts"
        / f"{safe_name(text)}.wav"
    )

    if not output_path.exists():
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        result = (
            google_tts_service.synthesise(
                text
            )
        )
        output_path.write_bytes(
            result.audio
        )
        print(
            "Synthesised "
            f"{text!r} in "
            f"{result.generation_seconds:.3f}s",
            flush=True,
        )

    return trim_outer_silence(
        decode_google_wav(
            output_path.read_bytes()
        )
    )


def write_pcm_wav(
    path: Path,
    samples: np.ndarray,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with wave.open(
        str(path),
        "wb",
    ) as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(
            TARGET_SAMPLE_RATE
        )
        wav_file.writeframes(
            samples.astype(
                "<i2"
            ).tobytes()
        )


def build_fixture_audio(
    fixture: FixtureDefinition,
    fixture_directory: Path,
) -> np.ndarray:
    audio_parts: list[np.ndarray] = [
        np.zeros(
            round(
                TARGET_SAMPLE_RATE
                * PRE_ROLL_DURATION_MS
                / 1000
            ),
            dtype="<i2",
        )
    ]

    for part_index, part_text in enumerate(
        fixture.parts
    ):
        audio_parts.append(
            load_or_synthesise_part(
                part_text,
                fixture_directory,
            )
        )

        if part_index < len(
            fixture.pauses_ms
        ):
            audio_parts.append(
                np.zeros(
                    round(
                        TARGET_SAMPLE_RATE
                        * fixture.pauses_ms[
                            part_index
                        ]
                        / 1000
                    ),
                    dtype="<i2",
                )
            )

    audio_parts.append(
        np.zeros(
            round(
                TARGET_SAMPLE_RATE
                * FINAL_TRAILING_SILENCE_MS
                / 1000
            ),
            dtype="<i2",
        )
    )
    samples = np.concatenate(
        audio_parts
    )
    write_pcm_wav(
        fixture_directory
        / f"{fixture.fixture_id}.wav",
        samples,
    )
    return samples


def calculate_rms(
    samples: np.ndarray,
) -> float:
    float_samples = (
        samples.astype(np.float32)
        / 32768.0
    )
    return float(
        np.sqrt(
            np.mean(
                float_samples
                * float_samples
            )
        )
    )


def simulate_worklet_vad(
    samples: np.ndarray,
    *,
    silence_threshold_ms: int,
) -> list[dict]:
    minimum_speech_samples = round(
        TARGET_SAMPLE_RATE
        * SPEECH_START_DURATION_MS
        / 1000
    )
    maximum_silence_samples = round(
        TARGET_SAMPLE_RATE
        * silence_threshold_ms
        / 1000
    )
    maximum_pre_roll_samples = round(
        TARGET_SAMPLE_RATE
        * PRE_ROLL_DURATION_MS
        / 1000
    )
    is_speech_active = False
    consecutive_speech_samples = 0
    consecutive_silence_samples = 0
    pre_roll_frames: list[np.ndarray] = []
    pre_roll_sample_count = 0
    active_frames: list[np.ndarray] = []
    segments: list[dict] = []

    padded_size = (
        (
            samples.size
            + WORKLET_FRAME_SAMPLES
            - 1
        )
        // WORKLET_FRAME_SAMPLES
        * WORKLET_FRAME_SAMPLES
    )
    padded_samples = np.pad(
        samples,
        (0, padded_size - samples.size),
    )

    for frame_start in range(
        0,
        padded_samples.size,
        WORKLET_FRAME_SAMPLES,
    ):
        frame = padded_samples[
            frame_start:
            frame_start
            + WORKLET_FRAME_SAMPLES
        ]
        frame_is_speech = (
            calculate_rms(frame)
            >= SPEECH_THRESHOLD
        )

        if not is_speech_active:
            copied_frame = frame.copy()
            pre_roll_frames.append(
                copied_frame
            )
            pre_roll_sample_count += (
                copied_frame.size
            )

            while (
                pre_roll_sample_count
                > maximum_pre_roll_samples
                and len(
                    pre_roll_frames
                )
                > 1
            ):
                removed_frame = (
                    pre_roll_frames.pop(0)
                )
                pre_roll_sample_count -= (
                    removed_frame.size
                )

            if frame_is_speech:
                consecutive_speech_samples += (
                    frame.size
                )
            else:
                consecutive_speech_samples = 0

            if (
                consecutive_speech_samples
                >= minimum_speech_samples
            ):
                is_speech_active = True
                consecutive_silence_samples = 0
                active_frames = [
                    item.copy()
                    for item
                    in pre_roll_frames
                ]
                pre_roll_frames = []
                pre_roll_sample_count = 0
                consecutive_speech_samples = 0

            continue

        active_frames.append(
            frame.copy()
        )

        if frame_is_speech:
            consecutive_silence_samples = 0
        else:
            consecutive_silence_samples += (
                frame.size
            )

        if (
            consecutive_silence_samples
            >= maximum_silence_samples
        ):
            segment_samples = np.concatenate(
                active_frames
            )
            segments.append(
                {
                    "samples": segment_samples,
                    "end_seconds": round(
                        (
                            frame_start
                            + frame.size
                        )
                        / TARGET_SAMPLE_RATE,
                        4,
                    ),
                    "duration_seconds": round(
                        segment_samples.size
                        / TARGET_SAMPLE_RATE,
                        4,
                    ),
                }
            )
            is_speech_active = False
            consecutive_silence_samples = 0
            consecutive_speech_samples = 0
            active_frames = []

    return segments


def normalise_words(
    text: str,
) -> list[str]:
    return re.findall(
        r"[a-z0-9]+",
        text.lower(),
    )


def word_error_rate(
    expected: str,
    actual: str,
) -> float:
    expected_words = normalise_words(
        expected
    )
    actual_words = normalise_words(
        actual
    )
    previous_row = list(
        range(
            len(actual_words) + 1
        )
    )

    for expected_index, expected_word in enumerate(
        expected_words,
        start=1,
    ):
        current_row = [expected_index]

        for actual_index, actual_word in enumerate(
            actual_words,
            start=1,
        ):
            substitution_cost = (
                0
                if expected_word
                == actual_word
                else 1
            )
            current_row.append(
                min(
                    current_row[-1] + 1,
                    previous_row[
                        actual_index
                    ]
                    + 1,
                    previous_row[
                        actual_index - 1
                    ]
                    + substitution_cost,
                )
            )

        previous_row = current_row

    if not expected_words:
        return (
            0.0
            if not actual_words
            else 1.0
        )

    return round(
        previous_row[-1]
        / len(expected_words),
        4,
    )


def append_transcript(
    existing: str,
    incoming: str,
) -> str:
    return " ".join(
        part
        for part in [
            existing.strip(),
            incoming.strip(),
        ]
        if part
    )


def evaluate_condition(
    *,
    fixture: FixtureDefinition,
    samples: np.ndarray,
    threshold_ms: int,
) -> dict:
    segments = simulate_worklet_vad(
        samples,
        silence_threshold_ms=threshold_ms,
    )
    conversation = create_conversation()
    accumulated_transcript = ""
    all_transcripts: list[str] = []
    segment_results: list[dict] = []
    premature_finalisations = 0
    finalised_turns = 0
    condition_error: dict | None = None

    for segment_index, segment in enumerate(
        segments
    ):
        transcription_started_at = (
            perf_counter()
        )
        transcription = (
            default_transcription_service
            .transcribe_pcm16(
                segment["samples"].tobytes(),
                sample_rate=TARGET_SAMPLE_RATE,
            )
        )
        transcription_seconds = (
            perf_counter()
            - transcription_started_at
        )
        all_transcripts.append(
            transcription.text
        )
        accumulated_transcript = (
            append_transcript(
                accumulated_transcript,
                transcription.text,
            )
        )
        is_last_segment = (
            segment_index
            == len(segments) - 1
        )
        turn_started_at = perf_counter()

        try:
            turn_result = process_turn_event(
                TurnBufferEvent(
                    conversation_id=(
                        conversation
                        .conversation_id
                    ),
                    partial_utterance=(
                        accumulated_transcript
                    ),
                    is_speech_active=False,
                    silence_duration_ms=(
                        threshold_ms
                    ),
                )
            )
        except Exception as error:
            turn_processing_seconds = (
                perf_counter()
                - turn_started_at
            )
            condition_error = {
                "segment_index": (
                    segment_index
                ),
                "error_type": (
                    type(error).__name__
                ),
                "error": str(error),
            }
            segment_results.append(
                {
                    "segment_index": (
                        segment_index
                    ),
                    "end_seconds": (
                        segment["end_seconds"]
                    ),
                    "duration_seconds": (
                        segment[
                            "duration_seconds"
                        ]
                    ),
                    "transcript": (
                        transcription.text
                    ),
                    "transcription_seconds": (
                        round(
                            transcription_seconds,
                            4,
                        )
                    ),
                    "accumulated_transcript": (
                        accumulated_transcript
                    ),
                    "decision": "error",
                    "should_finalise_turn": (
                        False
                    ),
                    "trp_probability": None,
                    "turn_processing_seconds": (
                        round(
                            turn_processing_seconds,
                            4,
                        )
                    ),
                    "is_last_segment": (
                        is_last_segment
                    ),
                    "error_type": (
                        condition_error[
                            "error_type"
                        ]
                    ),
                    "error": (
                        condition_error[
                            "error"
                        ]
                    ),
                }
            )
            break

        turn_processing_seconds = (
            perf_counter()
            - turn_started_at
        )

        if turn_result.should_finalise_turn:
            finalised_turns += 1

            if not is_last_segment:
                premature_finalisations += 1

            accumulated_transcript = ""

        segment_results.append(
            {
                "segment_index": (
                    segment_index
                ),
                "end_seconds": (
                    segment["end_seconds"]
                ),
                "duration_seconds": (
                    segment[
                        "duration_seconds"
                    ]
                ),
                "transcript": (
                    transcription.text
                ),
                "transcription_seconds": round(
                    transcription_seconds,
                    4,
                ),
                "accumulated_transcript": (
                    turn_result.state.transcript
                ),
                "decision": (
                    turn_result.decision
                ),
                "should_finalise_turn": (
                    turn_result
                    .should_finalise_turn
                ),
                "trp_probability": (
                    turn_result.state
                    .last_trp_probability
                ),
                "turn_processing_seconds": round(
                    turn_processing_seconds,
                    4,
                ),
                "is_last_segment": (
                    is_last_segment
                ),
            }
        )

    combined_transcript = " ".join(
        all_transcripts
    ).strip()
    final_segment_result = (
        segment_results[-1]
        if segment_results
        else None
    )
    first_segment_result = (
        segment_results[0]
        if segment_results
        else None
    )
    expected_internal_split = (
        bool(fixture.pauses_ms)
        and max(fixture.pauses_ms)
        >= threshold_ms
    )

    return {
        "success": (
            condition_error is None
        ),
        "error": condition_error,
        "fixture_id": (
            fixture.fixture_id
        ),
        "threshold_ms": threshold_ms,
        "expected_transcript": (
            fixture.expected_transcript
        ),
        "combined_transcript": (
            combined_transcript
        ),
        "word_error_rate": (
            word_error_rate(
                fixture.expected_transcript,
                combined_transcript,
            )
        ),
        "segment_count": len(segments),
        "acoustic_split": len(segments) > 1,
        "expected_internal_split": (
            expected_internal_split
        ),
        "premature_finalisations": (
            premature_finalisations
        ),
        "finalised_turns": (
            finalised_turns
        ),
        "final_segment_finalised": (
            bool(
                final_segment_result
                and final_segment_result
                .get(
                    "should_finalise_turn",
                    False,
                )
            )
        ),
        "first_segment_decision": (
            first_segment_result.get(
                "decision"
            )
            if first_segment_result
            else None
        ),
        "first_part_expected_complete": (
            fixture
            .first_part_expected_complete
        ),
        "guaranteed_final_pause_saving_ms": (
            600 - threshold_ms
        ),
        "segments": segment_results,
    }


def summarise_threshold(
    threshold_ms: int,
    results: list[dict],
) -> dict:
    threshold_results = [
        result
        for result in results
        if result["threshold_ms"]
        == threshold_ms
    ]
    successful_results = [
        result
        for result in threshold_results
        if result["success"]
    ]
    incomplete_split_results = [
        result
        for result
        in threshold_results
        if (
            result[
                "first_part_expected_complete"
            ]
            is False
            and result["acoustic_split"]
        )
    ]

    return {
        "threshold_ms": threshold_ms,
        "fixture_count": len(
            threshold_results
        ),
        "successful_conditions": len(
            successful_results
        ),
        "failed_conditions": (
            len(threshold_results)
            - len(successful_results)
        ),
        "acoustic_splits": sum(
            result["acoustic_split"]
            for result
            in threshold_results
        ),
        "premature_finalisations": sum(
            result[
                "premature_finalisations"
            ]
            for result
            in threshold_results
        ),
        "final_segments_finalised": sum(
            result[
                "final_segment_finalised"
            ]
            for result
            in threshold_results
        ),
        "incomplete_split_cases": len(
            incomplete_split_results
        ),
        "incomplete_splits_awaited": sum(
            result[
                "first_segment_decision"
            ]
            == "await_more_speech"
            for result
            in incomplete_split_results
        ),
        "mean_word_error_rate": (
            round(
                float(
                    np.mean(
                        [
                            result[
                                "word_error_rate"
                            ]
                            for result
                            in successful_results
                        ]
                    )
                ),
                4,
            )
            if successful_results
            else None
        ),
        "guaranteed_final_pause_saving_ms": (
            600 - threshold_ms
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture-directory",
        type=Path,
        default=Path(
            "tmp/vad_thresholds"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "tmp/latency/"
            "vad_threshold_benchmark.json"
        ),
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=int,
        default=THRESHOLDS_MS,
    )
    arguments = parser.parse_args()
    thresholds_ms = list(
        dict.fromkeys(
            arguments.thresholds
        )
    )

    if any(
        threshold_ms <= 0
        for threshold_ms in thresholds_ms
    ):
        raise ValueError(
            "VAD thresholds must be positive."
        )

    fixtures = {
        fixture.fixture_id: (
            build_fixture_audio(
                fixture,
                arguments.fixture_directory,
            )
        )
        for fixture in FIXTURES
    }

    # Warm Whisper and the configured TRP endpoint before
    # recording threshold conditions.
    warmup_fixture = FIXTURES[0]
    warmup_segments = simulate_worklet_vad(
        fixtures[
            warmup_fixture.fixture_id
        ],
        silence_threshold_ms=600,
    )
    default_transcription_service.transcribe_pcm16(
        warmup_segments[0][
            "samples"
        ].tobytes(),
        sample_rate=TARGET_SAMPLE_RATE,
    )
    trp_warmup_error = None

    try:
        predict_transition_relevance(
            partial_utterance=(
                warmup_fixture
                .expected_transcript
            ),
        )
    except Exception as error:
        trp_warmup_error = {
            "error_type": (
                type(error).__name__
            ),
            "error": str(error),
        }
        print(
            "TRP warm-up failed; threshold "
            "conditions will record any "
            "production timeout: "
            f"{type(error).__name__}: "
            f"{error}",
            flush=True,
        )

    print(
        "Whisper warm-up complete.",
        flush=True,
    )

    results: list[dict] = []

    for threshold_ms in thresholds_ms:
        for fixture in FIXTURES:
            result = evaluate_condition(
                fixture=fixture,
                samples=fixtures[
                    fixture.fixture_id
                ],
                threshold_ms=(
                    threshold_ms
                ),
            )
            results.append(result)
            print(
                f"{threshold_ms} ms "
                f"{fixture.fixture_id}: "
                f"success="
                f"{result['success']} "
                f"segments="
                f"{result['segment_count']} "
                f"premature="
                f"{result['premature_finalisations']} "
                f"final="
                f"{result['final_segment_finalised']} "
                f"wer="
                f"{result['word_error_rate']:.3f}",
                flush=True,
            )

    report = {
        "method": {
            "sample_rate": (
                TARGET_SAMPLE_RATE
            ),
            "worklet_frame_samples": (
                WORKLET_FRAME_SAMPLES
            ),
            "speech_threshold": (
                SPEECH_THRESHOLD
            ),
            "speech_start_duration_ms": (
                SPEECH_START_DURATION_MS
            ),
            "pre_roll_duration_ms": (
                PRE_ROLL_DURATION_MS
            ),
            "thresholds_ms": (
                thresholds_ms
            ),
            "semantic_check_minimum_ms": (
                300
            ),
            "fixture_voice": (
                "en-GB-Chirp3-HD-Aoede"
            ),
            "trp_warmup_error": (
                trp_warmup_error
            ),
        },
        "fixtures": [
            {
                "fixture_id": (
                    fixture.fixture_id
                ),
                "parts": fixture.parts,
                "pauses_ms": (
                    fixture.pauses_ms
                ),
                "expected_transcript": (
                    fixture
                    .expected_transcript
                ),
                "first_part_expected_complete": (
                    fixture
                    .first_part_expected_complete
                ),
            }
            for fixture in FIXTURES
        ],
        "threshold_summaries": [
            summarise_threshold(
                threshold_ms,
                results,
            )
            for threshold_ms
            in thresholds_ms
        ],
        "results": results,
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
    print(
        "\nThreshold summary:",
        flush=True,
    )
    print(
        json.dumps(
            report[
                "threshold_summaries"
            ],
            indent=2,
        ),
        flush=True,
    )
    print(
        f"Full report: {arguments.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
