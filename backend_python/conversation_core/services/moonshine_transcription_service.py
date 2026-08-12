from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from threading import Lock, Thread
from time import perf_counter
from typing import Any

import numpy as np

from moonshine_voice import (
    Transcriber,
    TranscriptEventListener,
    get_model_for_language,
)

from config import settings
from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
    TranscriptionSegment,
)


# A unique sentinel placed into the audio queue to tell the worker
# that no more PCM chunks will be supplied.
_STOP_AUDIO_WORKER = object()


@dataclass(frozen=True)
class QueuedPcmAudio:
    """
    One PCM audio chunk waiting to be passed to Moonshine.

    The browser currently sends:
    - signed 16-bit little-endian PCM;
    - 16 kHz;
    - mono audio.
    """

    pcm_bytes: bytes
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class CollectedTranscriptLine:
    """
    A completed Moonshine transcript line.

    Moonshine may divide one user turn into several lines when it
    detects pauses. We retain every completed line and join them when
    Smart Turn declares that the complete user turn has ended.
    """

    line_id: str
    start_seconds: float
    end_seconds: float
    text: str


class MoonshineTranscriptCollector(
    TranscriptEventListener
):
    """
    Receive Moonshine transcript events and retain completed lines.

    Moonshine callbacks may be invoked outside the FastAPI event-loop
    thread, so access to the collected lines is protected by a lock.
    """

    def __init__(self) -> None:
        super().__init__()

        self._lock = Lock()
        self._completed_lines: dict[
            str,
            CollectedTranscriptLine,
        ] = {}
        self._line_order: list[str] = []

    @staticmethod
    def _get_line_id(line: Any) -> str:
        raw_line_id = getattr(
            line,
            "line_id",
            None,
        )

        if raw_line_id is None:
            # This should rarely be needed, but gives us a stable
            # fallback for unexpected package-version differences.
            raw_line_id = id(line)

        return str(raw_line_id)

    def on_line_completed(self, event: Any) -> None:
        line = event.line
        text = str(
            getattr(line, "text", "")
        ).strip()

        if not text:
            return

        line_id = self._get_line_id(line)

        start_seconds = float(
            getattr(
                line,
                "start_time",
                0.0,
            )
            or 0.0
        )

        duration_seconds = float(
            getattr(
                line,
                "duration",
                0.0,
            )
            or 0.0
        )

        completed_line = CollectedTranscriptLine(
            line_id=line_id,
            start_seconds=start_seconds,
            end_seconds=(
                start_seconds
                + max(0.0, duration_seconds)
            ),
            text=text,
        )

        with self._lock:
            if line_id not in self._completed_lines:
                self._line_order.append(line_id)

            self._completed_lines[
                line_id
            ] = completed_line

    def build_response(
        self,
        *,
        language: str,
    ) -> TranscriptionResponse:
        """
        Convert all completed Moonshine lines into the schema already
        used by the rest of the application.
        """

        with self._lock:
            collected_lines = [
                self._completed_lines[line_id]
                for line_id in self._line_order
                if line_id in self._completed_lines
            ]

        segments = [
            TranscriptionSegment(
                start_seconds=line.start_seconds,
                end_seconds=line.end_seconds,
                text=line.text,
            )
            for line in collected_lines
        ]

        transcript = " ".join(
            line.text
            for line in collected_lines
        ).strip()

        duration_seconds = (
            max(
                (
                    line.end_seconds
                    for line in collected_lines
                ),
                default=0.0,
            )
            or None
        )

        return TranscriptionResponse(
            text=transcript,
            language=language,
            language_probability=None,
            duration_seconds=duration_seconds,
            segments=segments,
        )


class MoonshineStreamingSession:
    """
    One active streaming transcription session.

    PCM chunks are placed into a queue immediately. A dedicated worker
    thread passes them to Moonshine in the exact order received.

    This prevents Moonshine inference from blocking FastAPI's
    WebSocket event loop whenever a 20 ms browser audio chunk arrives.
    """

    def __init__(
        self,
        *,
        moonshine_stream: Any,
        language: str,
    ) -> None:
        self._stream = moonshine_stream
        self._language = language

        self._collector = (
            MoonshineTranscriptCollector()
        )

        self._audio_queue: Queue[
            QueuedPcmAudio | object
        ] = Queue()

        self._worker = Thread(
            target=self._consume_audio,
            name="moonshine-audio-worker",
            daemon=True,
        )

        self._state_lock = Lock()
        self._started = False
        self._finished = False
        self._worker_error: BaseException | None = None

    def start(self) -> None:
        with self._state_lock:
            if self._started:
                raise RuntimeError(
                    "Moonshine session has already started."
                )

            self._started = True

        self._stream.remove_all_listeners()
        self._stream.add_listener(
            self._collector
        )
        self._stream.start()
        self._worker.start()

    def add_pcm16(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int,
        channels: int = 1,
    ) -> None:
        """
        Queue one signed PCM16 little-endian audio chunk.

        This method deliberately performs no Moonshine inference. It
        validates the chunk and returns quickly so the WebSocket can
        continue receiving audio.
        """

        if not pcm_bytes:
            return

        if sample_rate <= 0:
            raise ValueError(
                "Audio sample rate must be positive."
            )

        if channels != 1:
            raise ValueError(
                "Moonshine streaming currently requires mono audio."
            )

        if len(pcm_bytes) % 2 != 0:
            raise ValueError(
                "PCM16 audio must contain an even number of bytes."
            )

        with self._state_lock:
            if not self._started:
                raise RuntimeError(
                    "Moonshine session has not started."
                )

            if self._finished:
                raise RuntimeError(
                    "Moonshine session has already finished."
                )

        self._audio_queue.put(
            QueuedPcmAudio(
                pcm_bytes=bytes(pcm_bytes),
                sample_rate=sample_rate,
                channels=channels,
            )
        )

    def _consume_audio(self) -> None:
        """
        Run inside the dedicated Moonshine worker thread.
        """

        try:
            while True:
                queued_item = self._audio_queue.get()

                if (
                    queued_item
                    is _STOP_AUDIO_WORKER
                ):
                    return

                if not isinstance(
                    queued_item,
                    QueuedPcmAudio,
                ):
                    continue

                pcm_samples = np.frombuffer(
                    queued_item.pcm_bytes,
                    dtype="<i2",
                )

                float_samples = (
                    pcm_samples.astype(
                        np.float32
                    )
                    / 32768.0
                )

                self._stream.add_audio(
                    float_samples,
                    queued_item.sample_rate,
                )

        except BaseException as error:
            self._worker_error = error

    def finish(
        self,
    ) -> TranscriptionResponse:
        """
        Finish all queued audio and return the final transcript.

        The sentinel is placed after every previously queued chunk, so
        the worker processes all received audio before stopping.
        """

        with self._state_lock:
            if not self._started:
                raise RuntimeError(
                    "Moonshine session has not started."
                )

            if self._finished:
                raise RuntimeError(
                    "Moonshine session has already finished."
                )

            self._finished = True

        self._audio_queue.put(
            _STOP_AUDIO_WORKER
        )

        self._worker.join(timeout=15.0)

        if self._worker.is_alive():
            raise TimeoutError(
                "Moonshine audio worker did not finish."
            )

        if self._worker_error is not None:
            raise RuntimeError(
                "Moonshine audio processing failed."
            ) from self._worker_error

        # Moonshine guarantees that stop() completes any currently
        # active transcript line and emits its completion event.
        self._stream.stop()

        return self._collector.build_response(
            language=self._language
        )

    def cancel(self) -> None:
        """
        Stop the session without returning its transcript.
        """

        with self._state_lock:
            if not self._started or self._finished:
                return

            self._finished = True

        self._audio_queue.put(
            _STOP_AUDIO_WORKER
        )

        self._worker.join(timeout=5.0)

        try:
            self._stream.stop()
        except Exception:
            # Cancellation is best-effort. The caller is intentionally
            # discarding this transcript.
            pass


class MoonshineStreamingTranscriptionService:
    """
    Own one resident Moonshine model and create lightweight streams
    from it.

    The expensive Transcriber/model object is loaded once. Individual
    user turns receive separate Stream objects that share those model
    resources.
    """

    def __init__(
        self,
        *,
        language: str = "en",
        model_arch: int | None = None,
        update_interval: float = 0.2,
    ) -> None:
        self.language = language
        self.model_arch = model_arch
        self.update_interval = (
            update_interval
        )

        self._transcriber: (
            Transcriber | None
        ) = None
        self._model_lock = Lock()

    def _get_transcriber(
        self,
    ) -> Transcriber:
        if self._transcriber is not None:
            return self._transcriber

        with self._model_lock:
            if self._transcriber is None:
                model_path, resolved_arch = (
                    get_model_for_language(
                        self.language,
                        self.model_arch,
                    )
                )

                options = {
                    # We do not currently need Moonshine to retain
                    # another copy of each line's PCM audio.
                    "return_audio_data": "false",
                    "identify_speakers": "false",
                }

                if (
                    settings.moonshine_save_input_wav_path
                    is not None
                ):
                    settings.moonshine_save_input_wav_path.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    options["save_input_wav_path"] = str(
                        settings.moonshine_save_input_wav_path
                    )

                self._transcriber = Transcriber(
                    model_path=model_path,
                    model_arch=resolved_arch,
                    update_interval=(
                        self.update_interval
                    ),
                    options=options,
                )

        return self._transcriber

    def warm_up(self) -> float:
        """
        Load the model before the first visitor begins speaking.
        """

        started_at = perf_counter()
        self._get_transcriber()

        return perf_counter() - started_at

    def create_session(
        self,
    ) -> MoonshineStreamingSession:
        transcriber = self._get_transcriber()

        moonshine_stream = (
            transcriber.create_stream(
                update_interval=(
                    self.update_interval
                ),
            )
        )

        session = MoonshineStreamingSession(
            moonshine_stream=moonshine_stream,
            language=self.language,
        )

        session.start()
        return session


default_moonshine_transcription_service = (
    MoonshineStreamingTranscriptionService(
        language=settings.moonshine_language,
        model_arch=settings.moonshine_model_arch,
        update_interval=(
            settings.moonshine_update_interval
        ),
    )
)
