from __future__ import annotations

from config import settings
from core_engine.services.tts_service import (
    TextToSpeechService,
)


def create_tts_service(
    backend: str | None = None,
) -> TextToSpeechService:
    selected_backend = (
        backend or settings.tts_backend
    ).strip().lower()

    if selected_backend == "google":
        from models.google_tts.google_tts_service import (
            GoogleTextToSpeechService,
        )

        return GoogleTextToSpeechService(
            default_voice_name=settings.tts_voice,
            default_language_code=settings.tts_language_code,
        )

    if selected_backend in {
        "kyutai",
        "kyutai_pocket",
        "pocket_tts",
    }:
        from models.pocket_tts.pocket_tts_service import (
            PocketTtsService,
        )

        return PocketTtsService(
            language=settings.tts_model,
            default_voice_name=settings.tts_voice,
            default_language_code=settings.tts_language_code,
            quantize=settings.tts_quantize,
        )

    raise ValueError(
        "Unsupported TTS backend: "
        f"{selected_backend}. Expected google or "
        "kyutai_pocket."
    )
