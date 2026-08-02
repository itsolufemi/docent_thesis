import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.api.routes_tts_stream import (
    create_tts_stream_router,
)


class FakeStreamingTtsService:
    def stream_synthesise(
        self,
        text,
        *,
        voice_name,
        language_code,
    ):
        self.request = {
            "text": text,
            "voice_name": voice_name,
            "language_code": language_code,
        }
        return iter([
            b"\x00\x00\x01\x00",
            b"\x02\x00",
        ])


class TtsStreamRouteTest(unittest.TestCase):
    def test_first_chunk_timing_is_reported_once(
        self,
    ) -> None:
        service = FakeStreamingTtsService()
        app = FastAPI()
        app.include_router(
            create_tts_stream_router(service)
        )

        with TestClient(app).websocket_connect(
            "/api/tts/stream"
        ) as websocket:
            websocket.send_json({
                "type": "synthesise",
                "payload": {
                    "text": "Hello from Docent.",
                },
            })

            started = websocket.receive_json()
            first_metadata = websocket.receive_json()
            first_audio = websocket.receive_bytes()
            second_metadata = websocket.receive_json()
            second_audio = websocket.receive_bytes()
            complete = websocket.receive_json()

        self.assertEqual(started["type"], "tts_started")
        self.assertEqual(
            first_metadata["type"],
            "tts_chunk",
        )
        self.assertTrue(
            first_metadata["payload"]["first_chunk"]
        )
        self.assertIsNotNone(
            first_metadata["payload"][
                "request_to_first_chunk_seconds"
            ]
        )
        self.assertEqual(first_audio, b"\x00\x00\x01\x00")

        self.assertFalse(
            second_metadata["payload"]["first_chunk"]
        )
        self.assertIsNone(
            second_metadata["payload"][
                "request_to_first_chunk_seconds"
            ]
        )
        self.assertEqual(second_audio, b"\x02\x00")

        self.assertEqual(complete["type"], "tts_complete")
        self.assertEqual(
            complete["payload"]["first_chunk_seconds"],
            first_metadata["payload"][
                "request_to_first_chunk_seconds"
            ],
        )
        self.assertEqual(
            complete["payload"]["chunk_count"],
            2,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
