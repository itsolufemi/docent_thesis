from __future__ import annotations

import io
import wave

from collections.abc import Iterator
from threading import Lock
from time import perf_counter
from typing import Any

import numpy as np

from config import settings
from conversation_core.services.tts_service import (
    SynthesisedSpeech,
)


DEFAULT_SAMPLE_RATE = 24_000


def _float_audio_to_pcm16(audio_chunk) -> bytes:
    audio = (
        audio_chunk.detach()
        .cpu()
        .float()
        .flatten()
        .numpy()
    )
    audio = np.clip(audio, -1.0, 1.0)
    pcm16 = np.round(audio * 32767.0).astype("<i2")
    return pcm16.tobytes()


def _pcm16_to_wav(
    pcm_audio: bytes,
    *,
    sample_rate: int,
) -> bytes:
    output = io.BytesIO()

    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm_audio)

    return output.getvalue()


class PocketTtsService:
    provider_name = "kyutai_pocket"
    recommended_prebuffer_ms = 30

    def __init__(
        self,
        *,
        language: str,
        default_voice_name: str,
        default_language_code: str,
        quantize: bool = False,
    ) -> None:
        self.language = language
        self.default_voice_name = default_voice_name
        self.default_language_code = default_language_code
        self.quantize = quantize
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._model: Any | None = None
        self._voice_states: dict[str, Any] = {}
        self._load_lock = Lock()
        self._generation_lock = Lock()

    def _ensure_model(self):
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is None:
                from pocket_tts import TTSModel

                self._model = TTSModel.load_model(
                    language=self.language,
                    quantize=self.quantize,
                )
                self.sample_rate = int(
                    self._model.sample_rate
                )

        return self._model

    def _get_voice_state(self, voice_name: str):
        model = self._ensure_model()
        existing = self._voice_states.get(voice_name)

        if existing is not None:
            return existing

        with self._load_lock:
            existing = self._voice_states.get(voice_name)

            if existing is None:
                existing = model.get_state_for_audio_prompt(
                    voice_name
                )
                self._voice_states[voice_name] = existing

        return existing

    def stream_synthesise(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        language_code: str | None = None,
    ) -> Iterator[bytes]:
        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError(
                "Text-to-speech input cannot be empty."
            )

        selected_voice = (
            voice_name or self.default_voice_name
        )
        model = self._ensure_model()
        voice_state = self._get_voice_state(
            selected_voice
        )

        with self._generation_lock:
            for audio_chunk in model.generate_audio_stream(
                voice_state,
                cleaned_text,
                copy_state=True,
            ):
                pcm_audio = _float_audio_to_pcm16(
                    audio_chunk
                )

                if pcm_audio:
                    yield pcm_audio

    def synthesise(
        self,
        text: str,
        *,
        voice_name: str | None = None,
        language_code: str | None = None,
    ) -> SynthesisedSpeech:
        cleaned_text = text.strip()

        if not cleaned_text:
            raise ValueError(
                "Text-to-speech input cannot be empty."
            )

        selected_voice = (
            voice_name or self.default_voice_name
        )
        selected_language = (
            language_code or self.default_language_code
        )
        started_at = perf_counter()
        pcm_audio = b"".join(
            self.stream_synthesise(
                cleaned_text,
                voice_name=selected_voice,
                language_code=selected_language,
            )
        )

        if not pcm_audio:
            raise RuntimeError(
                "Pocket TTS produced no audio."
            )

        return SynthesisedSpeech(
            audio=_pcm16_to_wav(
                pcm_audio,
                sample_rate=self.sample_rate,
            ),
            text=cleaned_text,
            voice_name=selected_voice,
            language_code=selected_language,
            sample_rate=self.sample_rate,
            generation_seconds=(
                perf_counter() - started_at
            ),
            character_count=len(cleaned_text),
            provider_name=self.provider_name,
        )

    def warm_up(self) -> dict:
        started_at = perf_counter()
        first_chunk_seconds: float | None = None
        chunk_count = 0
        audio_bytes = 0

        for chunk in self.stream_synthesise("Ready."):
            if chunk_count == 0:
                first_chunk_seconds = (
                    perf_counter() - started_at
                )

            chunk_count += 1
            audio_bytes += len(chunk)

        if chunk_count == 0:
            raise RuntimeError(
                "Pocket TTS warm-up produced no audio."
            )

        return {
            "provider": self.provider_name,
            "seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "first_chunk_seconds": (
                round(first_chunk_seconds, 4)
                if first_chunk_seconds is not None
                else None
            ),
            "chunk_count": chunk_count,
            "audio_bytes": audio_bytes,
            "sample_rate": self.sample_rate,
            "voice": self.default_voice_name,
        }

    def close(self) -> None:
        self._voice_states.clear()
        self._model = None


pocket_tts_service = PocketTtsService(
    language=settings.tts_model,
    default_voice_name=settings.tts_voice,
    default_language_code=(
        settings.tts_language_code
    ),
    quantize=settings.tts_quantize,
)
