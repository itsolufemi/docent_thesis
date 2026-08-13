from __future__ import annotations

from dataclasses import dataclass

from config import settings
from conversation_core.services.transcription_service import (
    BatchTranscriptionService,
    StreamingTranscriptionService,
)
from models.whisper_local.whisper_transcription_service import (
    default_local_whisper_transcription_service,
)


@dataclass(frozen=True)
class TranscriptionStack:
    """Selected transcription provider plus its batch fallback."""

    batch_service: BatchTranscriptionService
    streaming_service: StreamingTranscriptionService | None = None

    @property
    def provider_name(self) -> str:
        if self.streaming_service is not None:
            return self.streaming_service.provider_name

        return self.batch_service.provider_name

    def warm_up(self) -> float:
        if self.streaming_service is not None:
            return self.streaming_service.warm_up()

        return self.batch_service.warm_up()


def create_transcription_stack(
    backend: str | None = None,
) -> TranscriptionStack:
    selected_backend = (
        backend or settings.transcription_backend
    ).strip().lower()

    if selected_backend == "whisper":
        return TranscriptionStack(
            batch_service=(
                default_local_whisper_transcription_service
            ),
        )

    if selected_backend == "moonshine":
        from models.moonshine.moonshine_transcription_service import (
            default_moonshine_transcription_service,
        )

        return TranscriptionStack(
            batch_service=(
                default_local_whisper_transcription_service
            ),
            streaming_service=(
                default_moonshine_transcription_service
            ),
        )

    raise ValueError(
        "Unsupported transcription backend: "
        f"{selected_backend}. Expected moonshine or whisper."
    )


default_transcription_stack = create_transcription_stack()
