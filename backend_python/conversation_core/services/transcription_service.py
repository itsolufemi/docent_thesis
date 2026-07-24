from pathlib import Path
from threading import Lock

import numpy as np
from faster_whisper import WhisperModel

from config import settings
from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
    TranscriptionSegment,
)


class TranscriptionService:
    """
    Convert an audio file into text using faster-whisper.

    The model is loaded lazily so importing the FastAPI application
    does not immediately download or initialise Whisper.
    """

    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        compute_type: str,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type

        self._model: WhisperModel | None = None
        self._model_lock = Lock()
        self._transcription_lock = Lock()

    def _get_model(self) -> WhisperModel:
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is None:
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )

        return self._model

    def _transcribe_input(
        self,
        audio_input,
        *,
        language: str | None = "en",
    ) -> TranscriptionResponse:
        model = self._get_model()

        with self._transcription_lock:
            segment_generator, info = model.transcribe(
                audio_input,
                language=language,
                beam_size=1,
                condition_on_previous_text=False,
                vad_filter=False,
            )

            whisper_segments = list(segment_generator)

        segments = [
            TranscriptionSegment(
                start_seconds=segment.start,
                end_seconds=segment.end,
                text=segment.text.strip(),
            )
            for segment in whisper_segments
            if segment.text.strip()
        ]

        transcript = " ".join(
            segment.text
            for segment in segments
        ).strip()

        return TranscriptionResponse(
            text=transcript,
            language=getattr(
                info,
                "language",
                language,
            ),
            language_probability=getattr(
                info,
                "language_probability",
                None,
            ),
            duration_seconds=getattr(
                info,
                "duration",
                None,
            ),
            segments=segments,
        )

    def transcribe_file(
        self,
        audio_path: str | Path,
        *,
        language: str | None = "en",
    ) -> TranscriptionResponse:
        path = Path(audio_path)

        if not path.exists():
            raise FileNotFoundError(
                f"Audio file does not exist: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Audio path is not a file: {path}"
            )

        return self._transcribe_input(
            str(path),
            language=language,
        )

    def transcribe_pcm16(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int,
        channels: int = 1,
        language: str | None = "en",
    ) -> TranscriptionResponse:
        if not pcm_bytes:
            raise ValueError("PCM audio buffer is empty.")

        if sample_rate != 16_000:
            raise ValueError(
                "PCM transcription currently requires "
                "a 16000 Hz sample rate."
            )

        if channels != 1:
            raise ValueError(
                "PCM transcription currently requires mono audio."
            )

        if len(pcm_bytes) % 2 != 0:
            raise ValueError(
                "PCM16 audio must contain an even number of bytes."
            )

        pcm_samples = np.frombuffer(
            pcm_bytes,
            dtype="<i2",
        )
        float_samples = (
            pcm_samples.astype(np.float32)
            / 32768.0
        )

        return self._transcribe_input(
            float_samples,
            language=language,
        )


default_transcription_service = TranscriptionService(
    model_name=settings.whisper_model,
    device=settings.whisper_device,
    compute_type=settings.whisper_compute_type,
)
