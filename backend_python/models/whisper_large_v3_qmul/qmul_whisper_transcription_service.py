from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import Future
from queue import Queue
from threading import Lock, Thread
from time import perf_counter
from typing import Any

import websockets

from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
    TranscriptionSegment,
)
from models.whisper_large_v3_qmul.init_qmul_whisper import (
    ensure_qmul_whisper_ready,
)


QMUL_WHISPER_WS_URL = (
    "wss://hub.comp-teach.qmul.ac.uk/"
    "user/ec25326/proxy/8000/ws/transcribe"
)

SAMPLE_RATE = 16_000
CHANNELS = 1


_FINALIZE = object()
_CANCEL = object()
_STOP = object()


class QmulWhisperStreamingSession:
    """One utterance sent to the QMUL-hosted Whisper service."""

    def __init__(
        self,
        *,
        service: "QmulWhisperStreamingTranscriptionService",
    ) -> None:
        self._service = service
        self._lock = Lock()
        self._finished = False
        self._cancelled = False

    def add_pcm16(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int,
        channels: int = 1,
    ) -> None:
        if not pcm_bytes:
            return

        if sample_rate != SAMPLE_RATE:
            raise ValueError(
                "QMUL Whisper requires 16000 Hz PCM audio."
            )

        if channels != CHANNELS:
            raise ValueError(
                "QMUL Whisper requires mono PCM audio."
            )

        if len(pcm_bytes) % 2 != 0:
            raise ValueError(
                "PCM16 audio must contain an even number of bytes."
            )

        with self._lock:
            if self._finished:
                raise RuntimeError(
                    "QMUL Whisper session has already finished."
                )

            if self._cancelled:
                raise RuntimeError(
                    "QMUL Whisper session has been cancelled."
                )

        self._service._send_audio(bytes(pcm_bytes))

    def finish(self) -> TranscriptionResponse:
        with self._lock:
            if self._finished:
                raise RuntimeError(
                    "QMUL Whisper session has already finished."
                )

            if self._cancelled:
                raise RuntimeError(
                    "QMUL Whisper session was cancelled."
                )

            self._finished = True

        try:
            return self._service._finalize()
        finally:
            self._service._release_session(self)

    def cancel(self) -> None:
        with self._lock:
            if self._finished or self._cancelled:
                return

            self._cancelled = True

        try:
            self._service._reset_remote_buffer()
        finally:
            self._service._release_session(self)


class QmulWhisperStreamingTranscriptionService:
    """
    Persistent streaming provider backed by QMUL Whisper large-v3.

    A dedicated worker owns the asynchronous WebSocket while callers
    use the synchronous conversation-core transcription contract.
    """

    provider_name = "qmul_whisper_large_v3"

    def __init__(
        self,
        *,
        websocket_url: str = QMUL_WHISPER_WS_URL,
        finalize_timeout_seconds: float = 15.0,
    ) -> None:
        self.websocket_url = websocket_url
        self.finalize_timeout_seconds = finalize_timeout_seconds

        self._token = os.getenv("QMUL_JUPYTER_TOKEN")

        if not self._token:
            raise RuntimeError("QMUL_JUPYTER_TOKEN not found.")

        self._headers = {
            "Authorization": f"Bearer {self._token}",
        }

        self._worker_thread: Thread | None = None
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._command_queue: Queue[
            tuple[Any, Future[Any] | None]
        ] = Queue()
        self._ready_future: Future[bool] = Future()

        self._state_lock = Lock()
        self._active_session: QmulWhisperStreamingSession | None = None

        self._started = False
        self._closed = False

    def warm_up(self) -> float:
        """Start the QMUL runtime and persistent transcription WSS."""
        started_at = perf_counter()

        if self._started:
            return perf_counter() - started_at

        if self._closed:
            raise RuntimeError("QMUL Whisper service is closed.")

        asyncio.run(ensure_qmul_whisper_ready())
        self._start_worker()
        self._ready_future.result(timeout=30.0)
        self._started = True

        return perf_counter() - started_at

    def _start_worker(self) -> None:
        if (
            self._worker_thread is not None
            and self._worker_thread.is_alive()
        ):
            return

        self._worker_thread = Thread(
            target=self._worker_main,
            name="qmul-whisper-websocket",
            daemon=True,
        )
        self._worker_thread.start()

    def _worker_main(self) -> None:
        try:
            asyncio.run(self._worker_async())
        except BaseException as error:
            if not self._ready_future.done():
                self._ready_future.set_exception(error)

    async def _worker_async(self) -> None:
        self._worker_loop = asyncio.get_running_loop()

        async with websockets.connect(
            self.websocket_url,
            additional_headers=self._headers,
            ping_interval=20,
            ping_timeout=20,
        ) as websocket:
            if not self._ready_future.done():
                self._ready_future.set_result(True)

            while True:
                command, future = await asyncio.to_thread(
                    self._command_queue.get
                )

                if command is _STOP:
                    if future is not None:
                        future.set_result(True)
                    return

                if command is _FINALIZE:
                    try:
                        await websocket.send(
                            json.dumps({"type": "finalize"})
                        )
                        response = await websocket.recv()
                        result = json.loads(response)
                        transcription = self._build_response(result)

                        if future is not None:
                            future.set_result(transcription)
                    except BaseException as error:
                        if future is not None:
                            future.set_exception(error)
                    continue

                if command is _CANCEL:
                    try:
                        await websocket.send(
                            json.dumps({"type": "reset"})
                        )

                        if future is not None:
                            future.set_result(True)
                    except BaseException as error:
                        if future is not None:
                            future.set_exception(error)
                    continue

                if isinstance(command, bytes):
                    try:
                        await websocket.send(command)
                    except BaseException as error:
                        if future is not None:
                            future.set_exception(error)
                    else:
                        if future is not None:
                            future.set_result(True)

    def create_session(self) -> QmulWhisperStreamingSession:
        if not self._started:
            self.warm_up()

        if self._closed:
            raise RuntimeError("QMUL Whisper service is closed.")

        with self._state_lock:
            if self._active_session is not None:
                raise RuntimeError(
                    "A QMUL Whisper transcription session is "
                    "already active."
                )

            session = QmulWhisperStreamingSession(service=self)
            self._active_session = session
            return session

    def _release_session(
        self,
        session: QmulWhisperStreamingSession,
    ) -> None:
        with self._state_lock:
            if self._active_session is session:
                self._active_session = None

    def _send_audio(self, pcm_bytes: bytes) -> None:
        # FIFO ordering guarantees that all queued audio is sent before
        # a later finalisation command, without blocking the audio route.
        self._command_queue.put((pcm_bytes, None))

    def _finalize(self) -> TranscriptionResponse:
        future: Future[TranscriptionResponse] = Future()
        self._command_queue.put((_FINALIZE, future))
        return future.result(timeout=self.finalize_timeout_seconds)

    def _reset_remote_buffer(self) -> None:
        future: Future[bool] = Future()
        self._command_queue.put((_CANCEL, future))

        try:
            future.result(timeout=5.0)
        except Exception:
            # Cancellation is best-effort.
            pass

    @staticmethod
    def _build_response(result: dict[str, Any]) -> TranscriptionResponse:
        text = str(result.get("text", "")).strip()
        language = result.get("language", "en")

        duration = result.get("duration_seconds")
        if duration is None:
            duration = result.get("audio_duration")

        segments: list[TranscriptionSegment] = []

        for segment in result.get("segments") or []:
            segment_text = str(segment.get("text", "")).strip()

            if not segment_text:
                continue

            segments.append(
                TranscriptionSegment(
                    start_seconds=float(
                        segment.get(
                            "start_seconds",
                            segment.get("start", 0.0),
                        )
                    ),
                    end_seconds=float(
                        segment.get(
                            "end_seconds",
                            segment.get("end", 0.0),
                        )
                    ),
                    text=segment_text,
                )
            )

        return TranscriptionResponse(
            text=text,
            language=language,
            language_probability=result.get("language_probability"),
            duration_seconds=(
                float(duration) if duration is not None else None
            ),
            segments=segments,
        )

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        future: Future[bool] = Future()
        self._command_queue.put((_STOP, future))

        try:
            future.result(timeout=5.0)
        except Exception:
            pass

        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5.0)

        self._worker_thread = None
        self._worker_loop = None
        self._started = False


default_qmul_whisper_transcription_service = (
    QmulWhisperStreamingTranscriptionService()
)
