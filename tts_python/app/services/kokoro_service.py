from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from threading import Lock

import numpy as np


KOKORO_SAMPLE_RATE = 24_000


@dataclass(frozen=True)
class SpeechChunk:
    index: int
    text: str
    audio: np.ndarray
    sample_rate: int = KOKORO_SAMPLE_RATE


class KokoroService:
    def __init__(
        self,
        *,
        language_code: str = "b",
        default_voice: str = "bf_emma",
    ) -> None:
        self.language_code = language_code
        self.default_voice = default_voice

        self._pipeline = None
        self._load_lock = Lock()
        self._synthesis_lock = Lock()

    def _get_pipeline(self):
        """Load and retain the Kokoro pipeline on its first use."""
        if self._pipeline is not None:
            return self._pipeline

        with self._load_lock:
            if self._pipeline is None:
                from kokoro import KPipeline

                self._pipeline = KPipeline(
                    lang_code=self.language_code,
                )

        return self._pipeline

    def synthesise(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> Iterator[SpeechChunk]:
        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError(
                "Text-to-speech input cannot be empty."
            )

        if speed <= 0:
            raise ValueError(
                "Speech speed must be greater than zero."
            )

        selected_voice = voice or self.default_voice
        pipeline = self._get_pipeline()

        # Serial synthesis is the conservative starting point until
        # concurrent access to one pipeline has been validated.
        with self._synthesis_lock:
            generator = pipeline(
                cleaned_text,
                voice=selected_voice,
                speed=speed,
                split_pattern=r"(?<=[.!?])\s+",
            )

            output_index = 0

            for result in generator:
                graphemes, _phonemes, audio = result

                audio_array = np.asarray(
                    audio,
                    dtype=np.float32,
                )

                if audio_array.size == 0:
                    continue

                yield SpeechChunk(
                    index=output_index,
                    text=str(graphemes),
                    audio=audio_array,
                )

                output_index += 1


kokoro_service = KokoroService()
