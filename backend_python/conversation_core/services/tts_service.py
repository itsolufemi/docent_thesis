from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SynthesisedSpeech:
    audio: bytes
    text: str
    voice_name: str
    language_code: str
    sample_rate: int
    generation_seconds: float
    character_count: int
    provider_name: str


class TextToSpeechService(Protocol):
    provider_name: str
    default_voice_name: str
    default_language_code: str
    sample_rate: int
    recommended_prebuffer_ms: int

    def warm_up(self) -> dict:
        ...

    def synthesise(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        language_code: str | None = None,
    ) -> SynthesisedSpeech:
        ...

    def stream_synthesise(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        language_code: str | None = None,
    ) -> Iterator[bytes]:
        ...

    def close(self) -> None:
        ...
