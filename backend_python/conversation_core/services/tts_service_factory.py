from __future__ import annotations

from config import settings
from conversation_core.services.tts_service import (
    TextToSpeechService,
)


def create_tts_service(
    backend: str | None = None,
) -> TextToSpeechService:
    selected_backend = (
        backend or settings.tts_backend
    ).strip().lower()

    if selected_backend == "google":
        from conversation_core.services.google_tts_service import (
            google_tts_service,
        )

        google_tts_service.default_voice_name = (
            settings.tts_voice
        )
        google_tts_service.default_language_code = (
            settings.tts_language_code
        )
        return google_tts_service

    if selected_backend in {
        "kyutai",
        "kyutai_pocket",
        "pocket_tts",
    }:
        from conversation_core.services.pocket_tts_service import (
            pocket_tts_service,
        )

        return pocket_tts_service

    raise ValueError(
        "Unsupported TTS backend: "
        f"{selected_backend}. Expected google or "
        "kyutai_pocket."
    )


default_tts_service = create_tts_service()
