from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_ROOT),
    )


from models.google_tts.google_tts_service import (  # noqa: E402
    google_tts_service,
)


VOICE_NAMES = [
    "en-GB-Chirp3-HD-Aoede",
    "en-GB-Chirp3-HD-Achernar",
    "en-GB-Chirp3-HD-Vindemiatrix",
    "en-GB-Chirp3-HD-Zephyr",
    "en-GB-Chirp3-HD-Algenib",
]

TEST_TEXT = (
    "Welcome to the Wallace Collection. "
    "The Swing was painted by "
    "Jean-Honoré Fragonard in the "
    "eighteenth century. "
    "Would you like to hear more about it?"
)


def main() -> None:
    output_directory = (
        BACKEND_ROOT
        / "tmp"
        / "google_tts"
    )
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    for voice_name in VOICE_NAMES:
        result = google_tts_service.synthesise(
            TEST_TEXT,
            voice_name=voice_name,
        )

        safe_voice_name = (
            voice_name
            .replace(
                "en-GB-Chirp3-HD-",
                "",
            )
            .lower()
        )
        output_path = (
            output_directory
            / f"chirp_{safe_voice_name}.wav"
        )
        output_path.write_bytes(
            result.audio
        )

        print(
            f"{voice_name}: "
            f"{result.generation_seconds:.3f}s"
            f" -> {output_path}"
        )
        print(
            "TTS characters used:",
            result.character_count,
        )


if __name__ == "__main__":
    main()
