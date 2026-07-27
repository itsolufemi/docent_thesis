from pathlib import Path
import sys
import wave


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_ROOT),
    )


from conversation_core.services.google_tts_service import (  # noqa: E402
    DEFAULT_SAMPLE_RATE,
    google_tts_service,
)


def main() -> None:
    text = (
        "Welcome to the Wallace Collection. "
        "Today, we will begin with The Swing."
    )

    chunks = list(
        google_tts_service
        .stream_synthesise(text)
    )

    if not chunks:
        raise RuntimeError(
            "Google returned no streaming audio."
        )

    pcm_audio = b"".join(chunks)
    output_directory = (
        BACKEND_ROOT
        / "tmp"
        / "google_tts"
    )
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path = (
        output_directory
        / "chirp_stream_test.wav"
    )

    with wave.open(
        str(output_path),
        "wb",
    ) as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(
            DEFAULT_SAMPLE_RATE
        )
        wav_file.writeframes(pcm_audio)

    print({
        "chunks": len(chunks),
        "audio_bytes": len(pcm_audio),
        "output": str(output_path),
    })


if __name__ == "__main__":
    main()
