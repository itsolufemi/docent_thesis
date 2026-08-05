import sys
import threading
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
    provider_name = "fake"
    default_voice_name = "museum-guide"
    default_language_code = "en-GB"
    sample_rate = 24_000
    recommended_prebuffer_ms = 120

    def __init__(self) -> None:
        self.requests = []

    def stream_synthesise(
        self,
        text,
        *,
        voice_name,
        language_code,
    ):
        self.requests.append({
            "text": text,
            "voice_name": voice_name,
            "language_code": language_code,
        })
        return iter([b"\x00\x00\x01\x00", b"\x02\x00"])


class BlockingTtsService(FakeStreamingTtsService):
    recommended_prebuffer_ms = 120

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def stream_synthesise(self, *args, **kwargs):
        super().stream_synthesise(*args, **kwargs)

        def generate():
            self.release.wait(timeout=2)
            yield b"\x00\x00"

        return generate()


class TtsStreamRouteTest(unittest.TestCase):
    def test_ready_reports_selected_provider(self) -> None:
        app = FastAPI()
        app.include_router(
            create_tts_stream_router(
                FakeStreamingTtsService()
            )
        )

        with TestClient(app).websocket_connect(
            "/api/tts/stream"
        ) as websocket:
            ready = websocket.receive_json()

        self.assertEqual(ready["type"], "tts_ready")
        self.assertEqual(ready["payload"]["provider"], "fake")
        self.assertEqual(
            ready["payload"]["sample_rate"],
            24_000,
        )

    def test_two_syntheses_share_one_websocket(self) -> None:
        service = FakeStreamingTtsService()
        app = FastAPI()
        app.include_router(create_tts_stream_router(service))

        with TestClient(app).websocket_connect(
            "/api/tts/stream"
        ) as websocket:
            websocket.receive_json()
            completed_ids = []

            for synthesis_id, text in (
                ("synthesis-1", "First sentence."),
                ("synthesis-2", "Second sentence."),
            ):
                websocket.send_json({
                    "type": "synthesise",
                    "payload": {
                        "synthesis_id": synthesis_id,
                        "text": text,
                    },
                })
                started = websocket.receive_json()
                first_metadata = websocket.receive_json()
                websocket.receive_bytes()
                second_metadata = websocket.receive_json()
                websocket.receive_bytes()
                complete = websocket.receive_json()

                self.assertEqual(
                    started["payload"]["synthesis_id"],
                    synthesis_id,
                )
                self.assertTrue(
                    first_metadata["payload"]["first_chunk"]
                )
                self.assertFalse(
                    second_metadata["payload"]["first_chunk"]
                )
                completed_ids.append(
                    complete["payload"]["synthesis_id"]
                )

        self.assertEqual(
            completed_ids,
            ["synthesis-1", "synthesis-2"],
        )
        self.assertEqual(len(service.requests), 2)

    def test_cancellation_leaves_websocket_connected(self) -> None:
        service = BlockingTtsService()
        app = FastAPI()
        app.include_router(create_tts_stream_router(service))

        with TestClient(app).websocket_connect(
            "/api/tts/stream"
        ) as websocket:
            websocket.receive_json()
            websocket.send_json({
                "type": "synthesise",
                "payload": {
                    "synthesis_id": "cancel-me",
                    "text": "A long response.",
                },
            })
            websocket.receive_json()
            websocket.send_json({
                "type": "cancel",
                "payload": {
                    "synthesis_id": "cancel-me",
                },
            })
            cancelled = websocket.receive_json()
            service.release.set()
            websocket.send_json({
                "type": "synthesise",
                "payload": {
                    "synthesis_id": "after-cancel",
                    "text": "Continue on the same socket.",
                },
            })
            still_connected = websocket.receive_json()

        self.assertEqual(cancelled["type"], "tts_cancelled")
        self.assertEqual(
            cancelled["payload"]["synthesis_id"],
            "cancel-me",
        )
        self.assertEqual(still_connected["type"], "tts_started")
        self.assertEqual(
            still_connected["payload"]["synthesis_id"],
            "after-cancel",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
