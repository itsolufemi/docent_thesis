import sys
from pathlib import Path

import soundfile as sf


BACKEND_ROOT = Path(__file__).resolve().parents[3]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.whisper_large_v3_qmul.qmul_whisper_transcription_service import (  # noqa: E402
    default_qmul_whisper_transcription_service,
)


SAMPLE_RATE = 16_000
CHUNK_SAMPLES = 320
AUDIO_PATH = Path(__file__).with_name("test_6s.wav")


def main() -> None:
    audio, sample_rate = sf.read(
        AUDIO_PATH,
        dtype="int16",
    )

    if sample_rate != SAMPLE_RATE:
        raise ValueError(
            f"Expected {SAMPLE_RATE} Hz, got {sample_rate}."
        )

    if audio.ndim > 1:
        audio = audio[:, 0]

    service = default_qmul_whisper_transcription_service

    try:
        warm_up_seconds = service.warm_up()
        session = service.create_session()

        for start in range(0, len(audio), CHUNK_SAMPLES):
            session.add_pcm16(
                audio[start:start + CHUNK_SAMPLES].tobytes(),
                sample_rate=SAMPLE_RATE,
                channels=1,
            )

        result = session.finish()

        print(
            {
                "warm_up_seconds": round(warm_up_seconds, 3),
                "text": result.text,
                "language": result.language,
                "duration_seconds": result.duration_seconds,
                "segments": len(result.segments),
            }
        )
    finally:
        service.close()


if __name__ == "__main__":
    main()
