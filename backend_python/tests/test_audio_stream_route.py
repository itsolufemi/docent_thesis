import sys
import threading
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.api.routes_audio_stream import (
    create_audio_stream_router,
)
from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
)


class FakePCMTranscriptionService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe_pcm16(
        self,
        pcm_bytes,
        *,
        sample_rate,
        channels,
    ) -> TranscriptionResponse:
        self.calls.append(
            {
                "pcm_bytes": pcm_bytes,
                "sample_rate": sample_rate,
                "channels": channels,
            }
        )

        return TranscriptionResponse(
            text="Tell me about The Arab Tent.",
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )


class BlockingPCMTranscriptionService(
    FakePCMTranscriptionService
):
    def __init__(self, blocked_pcm: bytes) -> None:
        super().__init__()
        self.blocked_pcm = blocked_pcm
        self.blocked_call_started = threading.Event()
        self.release_blocked_call = threading.Event()

    def transcribe_pcm16(
        self,
        pcm_bytes,
        *,
        sample_rate,
        channels,
    ) -> TranscriptionResponse:
        self.calls.append(
            {
                "pcm_bytes": pcm_bytes,
                "sample_rate": sample_rate,
                "channels": channels,
            }
        )

        if pcm_bytes == self.blocked_pcm:
            self.blocked_call_started.set()

            if not self.release_blocked_call.wait(
                timeout=5
            ):
                raise TimeoutError(
                    "Blocked transcription was not released."
                )

        return TranscriptionResponse(
            text=f"Transcribed {len(pcm_bytes)} bytes.",
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )


class AudioStreamRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakePCMTranscriptionService()
        self.client = self.make_client(self.service)

    @staticmethod
    def make_client(service) -> TestClient:
        app = FastAPI()
        app.include_router(
            create_audio_stream_router(service)
        )
        return TestClient(app)

    def start_segment(
        self,
        websocket,
        segment_id: str,
    ) -> dict:
        websocket.send_json(
            {
                "type": "start_segment",
                "payload": {
                    "segment_id": segment_id,
                    "sample_rate": 16_000,
                    "channels": 1,
                    "sample_format": "pcm_s16le",
                },
            }
        )
        started = websocket.receive_json()
        self.assertEqual(
            started["type"],
            "audio_segment_started",
        )
        self.assertEqual(
            started["payload"]["segment_id"],
            segment_id,
        )
        return started

    def finalise_segment(
        self,
        websocket,
        segment_id: str,
    ) -> dict:
        websocket.send_json(
            {
                "type": "finalise_segment",
                "payload": {
                    "segment_id": segment_id,
                    "silence_duration_ms": 500,
                },
            }
        )

        started = websocket.receive_json()
        self.assertEqual(
            started["type"],
            "transcription_started",
        )
        self.assertEqual(
            started["payload"]["segment_id"],
            segment_id,
        )
        return started

    def receive_transcription(
        self,
        websocket,
        segment_id: str,
    ) -> dict:
        result = websocket.receive_json()
        self.assertEqual(
            result["type"],
            "audio_transcription",
        )
        self.assertEqual(
            result["payload"]["segment_id"],
            segment_id,
        )
        return result

    def test_segments_transcribe_pcm16_and_reset(self) -> None:
        first_pcm = b"\x00\x00" * 16_000
        second_pcm = b"\x01\x00" * 8_000

        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-1")
            websocket.send_bytes(first_pcm)
            self.finalise_segment(
                websocket,
                "segment-1",
            )
            first_result = self.receive_transcription(
                websocket,
                "segment-1",
            )

            self.assertEqual(
                first_result["payload"]["stream"][
                    "total_bytes"
                ],
                32_000,
            )
            self.assertEqual(
                first_result["payload"]["stream"][
                    "duration_seconds"
                ],
                1.0,
            )
            self.assertEqual(
                first_result["payload"][
                    "silence_duration_ms"
                ],
                500,
            )

            self.start_segment(websocket, "segment-2")
            websocket.send_bytes(second_pcm)
            self.finalise_segment(
                websocket,
                "segment-2",
            )
            second_result = self.receive_transcription(
                websocket,
                "segment-2",
            )

            self.assertEqual(
                second_result["payload"]["stream"][
                    "total_bytes"
                ],
                16_000,
            )
            self.assertEqual(
                second_result["payload"]["stream"][
                    "duration_seconds"
                ],
                0.5,
            )

        self.assertEqual(len(self.service.calls), 2)
        self.assertEqual(
            self.service.calls[0]["pcm_bytes"],
            first_pcm,
        )
        self.assertEqual(
            self.service.calls[0]["sample_rate"],
            16_000,
        )
        self.assertEqual(
            self.service.calls[0]["channels"],
            1,
        )
        self.assertEqual(
            self.service.calls[1]["pcm_bytes"],
            second_pcm,
        )

    def test_next_segment_is_received_while_prior_transcribes(
        self,
    ) -> None:
        first_pcm = b"\x01\x00" * 16_000
        second_pcm = b"\x02\x00" * 8_000
        service = BlockingPCMTranscriptionService(
            blocked_pcm=first_pcm,
        )
        client = self.make_client(service)

        with client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-1")
            websocket.send_bytes(first_pcm)
            self.finalise_segment(
                websocket,
                "segment-1",
            )
            self.assertTrue(
                service.blocked_call_started.wait(
                    timeout=2
                )
            )

            self.start_segment(websocket, "segment-2")
            websocket.send_bytes(second_pcm)
            self.finalise_segment(
                websocket,
                "segment-2",
            )

            second_result = self.receive_transcription(
                websocket,
                "segment-2",
            )
            self.assertEqual(
                second_result["payload"]["transcription"][
                    "text"
                ],
                "Transcribed 16000 bytes.",
            )

            service.release_blocked_call.set()
            first_result = self.receive_transcription(
                websocket,
                "segment-1",
            )
            self.assertEqual(
                first_result["payload"]["transcription"][
                    "text"
                ],
                "Transcribed 32000 bytes.",
            )

        self.assertEqual(len(service.calls), 2)

    def test_empty_segment_is_rejected_without_transcription(
        self,
    ) -> None:
        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-empty")
            websocket.send_json(
                {
                    "type": "finalise_segment",
                    "payload": {
                        "segment_id": "segment-empty",
                        "silence_duration_ms": 500,
                    },
                }
            )

            error = websocket.receive_json()

        self.assertEqual(error["type"], "audio_error")
        self.assertEqual(
            error["payload"]["segment_id"],
            "segment-empty",
        )
        self.assertIn(
            "No audio data",
            error["payload"]["detail"],
        )
        self.assertEqual(self.service.calls, [])

    def test_binary_data_before_start_is_rejected(self) -> None:
        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            websocket.send_bytes(b"\x00\x00")

            error = websocket.receive_json()

        self.assertEqual(error["type"], "audio_error")
        self.assertIn(
            "No active audio segment",
            error["payload"]["detail"],
        )

    def test_duplicate_segment_id_is_rejected(self) -> None:
        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-1")
            websocket.send_bytes(b"\x00\x00")
            self.finalise_segment(
                websocket,
                "segment-1",
            )
            self.receive_transcription(
                websocket,
                "segment-1",
            )

            websocket.send_json(
                {
                    "type": "start_segment",
                    "payload": {
                        "segment_id": "segment-1",
                    },
                }
            )
            error = websocket.receive_json()

        self.assertEqual(error["type"], "audio_error")
        self.assertIn(
            "already been used",
            error["payload"]["detail"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
