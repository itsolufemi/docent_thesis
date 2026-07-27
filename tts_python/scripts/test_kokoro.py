from pathlib import Path
import sys

import soundfile as sf


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.kokoro_service import (  # noqa: E402
    kokoro_service,
)


def main() -> None:
    output_directory = (
        PROJECT_ROOT / "generated_audio"
    )
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    test_text = (
        "Welcome to the Wallace Collection. "
        "The Swing was painted by "
        "Jean-Honoré Fragonard."
    )

    chunk_count = 0

    for chunk in kokoro_service.synthesise(
        test_text,
        voice="bf_emma",
        speed=1.0,
    ):
        output_path = (
            output_directory
            / f"kokoro_chunk_{chunk.index}.wav"
        )

        sf.write(
            output_path,
            chunk.audio,
            chunk.sample_rate,
        )

        duration_seconds = (
            chunk.audio.size
            / chunk.sample_rate
        )

        print(
            f"Chunk {chunk.index}:"
            f"\n  Text: {chunk.text}"
            f"\n  Samples: {chunk.audio.size}"
            f"\n  Duration: "
            f"{duration_seconds:.2f} seconds"
            f"\n  File: {output_path}"
        )

        chunk_count += 1

    if chunk_count == 0:
        raise RuntimeError(
            "Kokoro produced no audio chunks."
        )

    print(
        f"\nGenerated {chunk_count} audio chunk(s)."
    )


if __name__ == "__main__":
    main()
