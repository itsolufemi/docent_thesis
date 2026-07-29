from __future__ import annotations

import csv
import io
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile

import numpy as np
from dotenv import load_dotenv


WORKSPACE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = WORKSPACE_ROOT.parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend_python"
SUITE_AUDIO_ROOT = WORKSPACE_ROOT / "audio" / "suite"
MANIFEST_PATH = WORKSPACE_ROOT / "smart_turn_suite_manifest.csv"
TARGET_SAMPLE_RATE = 16_000

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from conversation_core.services.google_tts_service import (  # noqa: E402
    GoogleTextToSpeechService,
)


@dataclass(frozen=True)
class PhraseCase:
    case_id: str
    text: str
    expected_label: str
    category: str


VOICE_NAMES = [
    "en-GB-Chirp3-HD-Aoede",
    "en-GB-Chirp3-HD-Achernar",
]

PHRASE_CASES = [
    PhraseCase(
        "direct_request",
        "Tell me about The Arab Tent.",
        "complete",
        "complete_request",
    ),
    PhraseCase(
        "wh_question",
        "Who painted it?",
        "complete",
        "complete_question",
    ),
    PhraseCase(
        "tour_command",
        "Give me a highlights tour.",
        "complete",
        "complete_command",
    ),
    PhraseCase(
        "short_affirmation",
        "Yes.",
        "complete",
        "short_answer",
    ),
    PhraseCase(
        "contextual_answer",
        "Its history.",
        "complete",
        "contextual_answer",
    ),
    PhraseCase(
        "declarative",
        "The Arab Tent is remarkable.",
        "complete",
        "complete_declarative",
    ),
    PhraseCase(
        "polite_completion",
        "Please continue.",
        "complete",
        "complete_command",
    ),
    PhraseCase(
        "short_rejection",
        "No, thank you.",
        "complete",
        "short_answer",
    ),
    PhraseCase(
        "trailing_object",
        "Could you tell me about...",
        "incomplete",
        "trailing_object",
    ),
    PhraseCase(
        "trailing_because",
        "I wanted to ask because...",
        "incomplete",
        "trailing_conjunction",
    ),
    PhraseCase(
        "trailing_determiner",
        "Tell me about the...",
        "incomplete",
        "trailing_determiner",
    ),
    PhraseCase(
        "trailing_copula",
        "I think the painting is...",
        "incomplete",
        "trailing_copula",
    ),
    PhraseCase(
        "trailing_and",
        "And what about...",
        "incomplete",
        "trailing_conjunction",
    ),
    PhraseCase(
        "conditional_clause",
        "If we move to the next room...",
        "incomplete",
        "subordinate_clause",
    ),
    PhraseCase(
        "relative_clause",
        "The artist who painted it...",
        "incomplete",
        "relative_clause",
    ),
    PhraseCase(
        "question_stem",
        "Could you explain how...",
        "incomplete",
        "question_stem",
    ),
]

EXISTING_CASES = [
    (
        "human_voice_request",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "latency"
        / "voice_request.wav",
        "complete",
        "Tell me about The Swing.",
        "human_complete_request",
    ),
    (
        "pause_complete_request",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "complete_request.wav",
        "complete",
        "Tell me about The Arab Tent.",
        "synthetic_complete_request",
    ),
    (
        "pause_250_continuation",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "incomplete_pause_250.wav",
        "complete",
        "Could you tell me about The Arab Tent?",
        "internal_pause",
    ),
    (
        "pause_350_continuation",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "incomplete_pause_350.wav",
        "complete",
        "Could you tell me about The Arab Tent?",
        "internal_pause",
    ),
    (
        "pause_450_continuation",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "incomplete_pause_450.wav",
        "complete",
        "Could you tell me about The Arab Tent?",
        "internal_pause",
    ),
    (
        "unfinished_clause_then_completion",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "unfinished_clause_pause_350.wav",
        "complete",
        "I think that the painting is beautiful.",
        "internal_pause",
    ),
    (
        "existing_trailing_object",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "parts"
        / "could_you_tell_me_about.wav",
        "incomplete",
        "Could you tell me about",
        "trailing_object",
    ),
    (
        "existing_subordinate_stem",
        REPOSITORY_ROOT
        / "backend_python"
        / "tmp"
        / "vad_thresholds"
        / "parts"
        / "i_think_that.wav",
        "incomplete",
        "I think that",
        "subordinate_clause",
    ),
]


def safe_name(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        value.lower(),
    ).strip("_")


def convert_google_wav_to_pcm16(
    wav_bytes: bytes,
) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        samples = np.frombuffer(
            source.readframes(frame_count),
            dtype="<i2",
        ).astype(np.float32)

    if sample_width != 2:
        raise ValueError("Expected Google LINEAR16 audio.")

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    if sample_rate != TARGET_SAMPLE_RATE:
        target_size = round(
            samples.size
            * TARGET_SAMPLE_RATE
            / sample_rate
        )
        samples = np.interp(
            np.linspace(
                0,
                max(samples.size - 1, 0),
                target_size,
            ),
            np.arange(samples.size),
            samples,
        )

    pcm16 = np.clip(
        np.rint(samples),
        -32768,
        32767,
    ).astype("<i2")

    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(TARGET_SAMPLE_RATE)
        destination.writeframes(pcm16.tobytes())
    return output.getvalue()


def main() -> None:
    SUITE_AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
    service = GoogleTextToSpeechService()
    rows: list[dict[str, str]] = []
    failures: list[str] = []

    for voice_name in VOICE_NAMES:
        voice_suffix = safe_name(
            voice_name.replace("en-GB-Chirp3-HD-", "")
        )

        for case in PHRASE_CASES:
            output_name = (
                f"{case.case_id}__{voice_suffix}.wav"
            )
            output_path = SUITE_AUDIO_ROOT / output_name

            if not output_path.exists():
                try:
                    result = service.synthesise(
                        case.text,
                        voice_name=voice_name,
                    )
                    output_path.write_bytes(
                        convert_google_wav_to_pcm16(
                            result.audio
                        )
                    )
                    print(
                        f"Synthesised {output_name}: "
                        f"{result.generation_seconds:.3f}s"
                    )
                except Exception as error:
                    failures.append(
                        f"{case.case_id}/{voice_name}: {error}"
                    )
                    continue

            rows.append(
                {
                    "case_id": (
                        f"{case.case_id}__{voice_suffix}"
                    ),
                    "audio_path": str(
                        output_path.relative_to(
                            WORKSPACE_ROOT
                        )
                    ).replace("\\", "/"),
                    "expected_label": case.expected_label,
                    "transcript": case.text,
                    "category": case.category,
                    "source": "google_chirp",
                    "voice": voice_name,
                }
            )

    for (
        case_id,
        source_path,
        expected_label,
        transcript,
        category,
    ) in EXISTING_CASES:
        if not source_path.is_file():
            failures.append(
                f"{case_id}: missing {source_path}"
            )
            continue

        output_path = (
            SUITE_AUDIO_ROOT
            / f"{case_id}.wav"
        )
        copyfile(source_path, output_path)
        rows.append(
            {
                "case_id": case_id,
                "audio_path": str(
                    output_path.relative_to(
                        WORKSPACE_ROOT
                    )
                ).replace("\\", "/"),
                "expected_label": expected_label,
                "transcript": transcript,
                "category": category,
                "source": (
                    "human"
                    if case_id == "human_voice_request"
                    else "existing_fixture"
                ),
                "voice": "",
            }
        )

    with MANIFEST_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "audio_path",
                "expected_label",
                "transcript",
                "category",
                "source",
                "voice",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    complete_count = sum(
        row["expected_label"] == "complete"
        for row in rows
    )
    incomplete_count = len(rows) - complete_count
    print(
        {
            "manifest": str(MANIFEST_PATH),
            "cases": len(rows),
            "complete": complete_count,
            "incomplete": incomplete_count,
            "failures": failures,
        }
    )

    if failures:
        raise RuntimeError(
            "One or more suite assets could not be built."
        )


if __name__ == "__main__":
    main()
