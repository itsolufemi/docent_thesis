from __future__ import annotations

from collections.abc import Iterator
from threading import Lock
from time import perf_counter

from google.cloud import texttospeech

from conversation_core.services.tts_service import (
    SynthesisedSpeech,
)


DEFAULT_LANGUAGE_CODE = "en-GB"
DEFAULT_VOICE_NAME = "en-GB-Chirp3-HD-Aoede"
DEFAULT_SAMPLE_RATE = 24_000


class GoogleTextToSpeechService:
    provider_name = "google"
    def __init__(
        self,
        *,
        default_voice_name: str = (
            DEFAULT_VOICE_NAME
        ),
        default_language_code: str = (
            DEFAULT_LANGUAGE_CODE
        ),
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.default_voice_name = default_voice_name
        self.default_language_code = (
            default_language_code
        )
        self.sample_rate = sample_rate

        self._client: (
            texttospeech.TextToSpeechClient
            | None
        ) = None
        self._client_lock = Lock()

    def _get_client(
        self,
    ) -> texttospeech.TextToSpeechClient:
        if self._client is not None:
            return self._client

        with self._client_lock:
            if self._client is None:
                self._client = (
                    texttospeech
                    .TextToSpeechClient()
                )

        return self._client

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
            voice_name
            or self.default_voice_name
        )
        selected_language = (
            language_code
            or self.default_language_code
        )

        client = self._get_client()

        synthesis_input = (
            texttospeech.SynthesisInput(
                text=cleaned_text,
            )
        )
        voice = (
            texttospeech.VoiceSelectionParams(
                language_code=selected_language,
                name=selected_voice,
            )
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=(
                texttospeech.AudioEncoding.LINEAR16
            ),
            sample_rate_hertz=self.sample_rate,
        )

        started_at = perf_counter()

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        generation_seconds = (
            perf_counter() - started_at
        )

        if not response.audio_content:
            raise RuntimeError(
                "Google Cloud returned no audio."
            )

        return SynthesisedSpeech(
            audio=response.audio_content,
            text=cleaned_text,
            voice_name=selected_voice,
            language_code=selected_language,
            sample_rate=self.sample_rate,
            generation_seconds=generation_seconds,
            character_count=len(cleaned_text),
            provider_name=self.provider_name,
        )

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
            voice_name
            or self.default_voice_name
        )
        selected_language = (
            language_code
            or self.default_language_code
        )

        client = self._get_client()

        streaming_config = (
            texttospeech.StreamingSynthesizeConfig(
                voice=(
                    texttospeech
                    .VoiceSelectionParams(
                        language_code=(
                            selected_language
                        ),
                        name=selected_voice,
                    )
                ),
                streaming_audio_config=(
                    texttospeech
                    .StreamingAudioConfig(
                        audio_encoding=(
                            texttospeech
                            .AudioEncoding
                            .PCM
                        ),
                        sample_rate_hertz=(
                            self.sample_rate
                        ),
                    )
                ),
            )
        )
        config_request = (
            texttospeech
            .StreamingSynthesizeRequest(
                streaming_config=(
                    streaming_config
                )
            )
        )
        input_request = (
            texttospeech
            .StreamingSynthesizeRequest(
                input=(
                    texttospeech
                    .StreamingSynthesisInput(
                        text=cleaned_text,
                    )
                )
            )
        )

        def request_generator():
            yield config_request
            yield input_request

        responses = client.streaming_synthesize(
            request_generator()
        )

        for response in responses:
            audio_content = response.audio_content

            if audio_content:
                yield bytes(audio_content)

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
                "Google TTS warm-up returned no audio."
            )

        return {
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
        }

    def close(self) -> None:
        with self._client_lock:
            client = self._client
            self._client = None

        if client is None:
            return

        transport = getattr(client, "transport", None)
        close = getattr(transport, "close", None)

        if callable(close):
            close()


google_tts_service = GoogleTextToSpeechService()
