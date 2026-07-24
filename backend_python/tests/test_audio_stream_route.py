import sys
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


class AudioStreamRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakePCMTranscriptionService()
        app = FastAPI()
        app.include_router(
            create_audio_stream_router(self.service)
        )
        self.client = TestClient(app)

    def start_stream(self, websocket) -> None:
        websocket.send_json(
            {
                "type": "start_audio",
                "payload": {
                    "sample_rate": 16_000,
                    "channels": 1,
                    "sample_format": "pcm_s16le",
                },
            }
        )
        started = websocket.receive_json()
        self.assertEqual(
            started["type"],
            "audio_stream_started",
        )

    def stop_and_receive_transcription(self, websocket) -> dict:
        websocket.send_json(
            {
                "type": "stop_audio",
                "payload": {},
            }
        )

        started = websocket.receive_json()
        self.assertEqual(
            started["type"],
            "transcription_started",
        )

        result = websocket.receive_json()
        self.assertEqual(
            result["type"],
            "audio_transcription",
        )

        return result

    def test_stream_transcribes_pcm16_and_resets(self) -> None:
        first_pcm = b"\x00\x00" * 16_000
        second_pcm = b"\x01\x00" * 8_000

        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_stream(websocket)
            websocket.send_bytes(first_pcm)
            first_result = self.stop_and_receive_transcription(
                websocket
            )

            self.assertEqual(
                first_result["payload"]["stream"]["total_bytes"],
                32_000,
            )
            self.assertEqual(
                first_result["payload"]["stream"][
                    "duration_seconds"
                ],
                1.0,
            )
            self.assertEqual(
                first_result["payload"]["transcription"]["text"],
                "Tell me about The Arab Tent.",
            )

            self.start_stream(websocket)
            websocket.send_bytes(second_pcm)
            second_result = self.stop_and_receive_transcription(
                websocket
            )

            self.assertEqual(
                second_result["payload"]["stream"]["total_bytes"],
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

    def test_empty_stream_is_rejected_without_transcription(self) -> None:
        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_stream(websocket)
            websocket.send_json(
                {
                    "type": "stop_audio",
                    "payload": {},
                }
            )

            error = websocket.receive_json()

        self.assertEqual(error["type"], "audio_error")
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
            "has not been started",
            error["payload"]["detail"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
