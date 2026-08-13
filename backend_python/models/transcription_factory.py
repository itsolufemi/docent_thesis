from __future__ import annotations

from dataclasses import dataclass

from config import settings
from conversation_core.services.transcription_service import (
    BatchTranscriptionService,
    PcmTranscriptionService,
    StreamingTranscriptionService,
)
from models.whisper_local.whisper_transcription_service import (
    default_local_whisper_transcription_service,
)


@dataclass(frozen=True)
class TranscriptionStack:
    """Selected provider, upload service, and live PCM fallback."""

    batch_service: BatchTranscriptionService
    streaming_service: StreamingTranscriptionService | None = None
    fallback_service: PcmTranscriptionService | None = None

    @property
    def live_fallback_service(self) -> PcmTranscriptionService:
        return self.fallback_service or self.batch_service

    @property
    def provider_name(self) -> str:
        if self.streaming_service is not None:
            return self.streaming_service.provider_name

        return self.batch_service.provider_name

    def warm_up(self) -> float:
        if self.streaming_service is not None:
            return self.streaming_service.warm_up()

        return self.batch_service.warm_up()

    def close(self) -> None:
        if self.streaming_service is None:
            return

        close_method = getattr(
            self.streaming_service,
            "close",
            None,
        )

        if callable(close_method):
            close_method()


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

    if selected_backend == "qmul_whisper":
        from models.moonshine.moonshine_transcription_service import (
            default_moonshine_transcription_service,
        )
        from models.whisper_large_v3_qmul.qmul_whisper_transcription_service import (
            default_qmul_whisper_transcription_service,
        )

        return TranscriptionStack(
            batch_service=(
                default_local_whisper_transcription_service
            ),
            streaming_service=(
                default_qmul_whisper_transcription_service
            ),
            fallback_service=(
                default_moonshine_transcription_service
            ),
        )

    raise ValueError(
        "Unsupported transcription backend: "
        f"{selected_backend}. Expected moonshine, whisper, "
        "or qmul_whisper."
    )


default_transcription_stack = create_transcription_stack()
