from __future__ import annotations

from pathlib import Path
from typing import Protocol

from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
)


class PcmTranscriptionService(Protocol):
    """Provider-independent fallback contract for completed PCM."""

    provider_name: str

    def warm_up(self) -> float:
        ...

    def transcribe_pcm16(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int,
        channels: int = 1,
        language: str | None = "en",
    ) -> TranscriptionResponse:
        ...


class BatchTranscriptionService(PcmTranscriptionService, Protocol):
    """Provider-independent contract for files and completed PCM."""

    def transcribe_file(
        self,
        audio_path: str | Path,
        *,
        language: str | None = "en",
    ) -> TranscriptionResponse:
        ...


class StreamingTranscriptionSession(Protocol):
    """One provider-independent live PCM transcription session."""

    def add_pcm16(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int,
        channels: int = 1,
    ) -> None:
        ...

    def finish(self) -> TranscriptionResponse:
        ...

    def cancel(self) -> None:
        ...


class StreamingTranscriptionService(Protocol):
    """Factory contract for live transcription sessions."""

    provider_name: str

    def warm_up(self) -> float:
        ...

    def create_session(
        self,
    ) -> StreamingTranscriptionSession:
        ...
