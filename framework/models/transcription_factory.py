from __future__ import annotations

from dataclasses import dataclass

from config import settings
from core_engine.services.transcription_service import (
    BatchTranscriptionService,
    PcmTranscriptionService,
    StreamingTranscriptionService,
)
from models.whisper_local.whisper_transcription_service import (
    LocalWhisperTranscriptionService,
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
        closed_service_ids: set[int] = set()
        errors: list[Exception] = []

        for service in (
            self.streaming_service,
            self.fallback_service,
            self.batch_service,
        ):
            if service is None or id(service) in closed_service_ids:
                continue

            closed_service_ids.add(id(service))
            close_method = getattr(service, "close", None)

            if not callable(close_method):
                continue

            try:
                close_method()
            except Exception as error:
                errors.append(error)

        if errors:
            raise ExceptionGroup(
                "One or more transcription services failed to close.",
                errors,
            )


def create_transcription_stack(
    backend: str | None = None,
) -> TranscriptionStack:
    selected_backend = (
        backend or settings.transcription_backend
    ).strip().lower()

    local_whisper_service = LocalWhisperTranscriptionService(
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )

    if selected_backend == "whisper":
        return TranscriptionStack(
            batch_service=local_whisper_service,
        )

    if selected_backend == "moonshine":
        from models.moonshine.moonshine_transcription_service import (
            MoonshineStreamingTranscriptionService,
        )

        return TranscriptionStack(
            batch_service=local_whisper_service,
            streaming_service=MoonshineStreamingTranscriptionService(
                language=settings.moonshine_language,
                model_arch=settings.moonshine_model_arch,
                update_interval=settings.moonshine_update_interval,
            ),
        )

    if selected_backend == "qmul_whisper":
        from models.moonshine.moonshine_transcription_service import (
            MoonshineStreamingTranscriptionService,
        )
        from models.whisper_large_v3_qmul.qmul_whisper_transcription_service import (
            QmulWhisperStreamingTranscriptionService,
        )

        return TranscriptionStack(
            batch_service=local_whisper_service,
            streaming_service=QmulWhisperStreamingTranscriptionService(),
            fallback_service=MoonshineStreamingTranscriptionService(
                language=settings.moonshine_language,
                model_arch=settings.moonshine_model_arch,
                update_interval=settings.moonshine_update_interval,
            ),
        )

    raise ValueError(
        "Unsupported transcription backend: "
        f"{selected_backend}. Expected moonshine, whisper, "
        "or qmul_whisper."
    )
