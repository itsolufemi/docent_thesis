import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from server import app


class AudioStreamRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_stream_returns_pcm16_summary_and_resets(self) -> None:
        with self.client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
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

            websocket.send_bytes(b"\x00\x00" * 16_000)
            websocket.send_json(
                {
                    "type": "stop_audio",
                    "payload": {},
                }
            )
            completed = websocket.receive_json()

            self.assertEqual(
                completed["type"],
                "audio_stream_complete",
            )
            self.assertEqual(
                completed["payload"]["total_bytes"],
                32_000,
            )
            self.assertEqual(
                completed["payload"]["total_samples"],
                16_000,
            )
            self.assertEqual(
                completed["payload"]["duration_seconds"],
                1.0,
            )

            websocket.send_json(
                {
                    "type": "start_audio",
                    "payload": {},
                }
            )
            websocket.receive_json()
            websocket.send_bytes(b"\x01\x00" * 8_000)
            websocket.send_json(
                {
                    "type": "stop_audio",
                    "payload": {},
                }
            )
            second_completed = websocket.receive_json()

            self.assertEqual(
                second_completed["payload"]["total_bytes"],
                16_000,
            )
            self.assertEqual(
                second_completed["payload"]["duration_seconds"],
                0.5,
            )

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
