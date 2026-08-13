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
from conversation_core.services.smart_turn_service import (
    SmartTurnPrediction,
)


class FakePCMTranscriptionService:
    provider_name = "fake_batch"

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


class FakeSmartTurnService:
    def __init__(
        self,
        predictions: list[bool],
    ) -> None:
        self.predictions = list(predictions)
        self.calls: list[bytes] = []

    def predict(
        self,
        pcm_audio,
        sample_rate=16_000,
        *,
        channels=1,
    ) -> SmartTurnPrediction:
        self.calls.append(pcm_audio)
        turn_complete = self.predictions.pop(0)
        probability = 0.9 if turn_complete else 0.1

        return SmartTurnPrediction(
            completion_probability=probability,
            turn_complete=turn_complete,
            feature_extraction_seconds=0.01,
            inference_seconds=0.02,
            total_seconds=0.03,
        )


class BlockingSmartTurnService(FakeSmartTurnService):
    def __init__(self) -> None:
        super().__init__([True])
        self.call_started = threading.Event()
        self.release_call = threading.Event()

    def predict(
        self,
        pcm_audio,
        sample_rate=16_000,
        *,
        channels=1,
    ) -> SmartTurnPrediction:
        self.call_started.set()

        if not self.release_call.wait(timeout=5):
            raise TimeoutError(
                "Blocked Smart Turn call was not released."
            )

        return super().predict(
            pcm_audio,
            sample_rate,
            channels=channels,
        )


class AudioStreamRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakePCMTranscriptionService()
        self.client = self.make_client(self.service)

    @staticmethod
    def make_client(
        service,
        smart_turn_service=None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(
            create_audio_stream_router(
                service,
                smart_turn_service,
            )
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

    def test_incomplete_candidate_preserves_continuation_audio(
        self,
    ) -> None:
        first_pcm = b"\x01\x00" * 8_000
        continuation_pcm = b"\x02\x00" * 8_000
        smart_turn = FakeSmartTurnService(
            [False, True]
        )
        client = self.make_client(
            self.service,
            smart_turn,
        )

        with client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-1")
            websocket.send_bytes(first_pcm)
            websocket.send_json(
                {
                    "type": "candidate_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 1,
                        "silence_duration_ms": 500,
                    },
                }
            )
            self.assertEqual(
                websocket.receive_json()["type"],
                "smart_turn_started",
            )
            first_result = websocket.receive_json()
            self.assertEqual(
                first_result["type"],
                "smart_turn_result",
            )
            self.assertFalse(
                first_result["payload"]["turn_complete"]
            )
            self.assertEqual(
                websocket.receive_json()["type"],
                "awaiting_speech_continuation",
            )

            websocket.send_json(
                {
                    "type": "finalise_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 1,
                        "silence_duration_ms": 500,
                    },
                }
            )
            premature_finalisation = (
                websocket.receive_json()
            )
            self.assertEqual(
                premature_finalisation["type"],
                "audio_error",
            )
            self.assertIn(
                "not current and confirmed complete",
                premature_finalisation["payload"][
                    "detail"
                ],
            )
            self.assertEqual(self.service.calls, [])

            websocket.send_json(
                {
                    "type": "speech_resumed",
                    "payload": {
                        "segment_id": "segment-1",
                    },
                }
            )
            websocket.send_bytes(continuation_pcm)
            websocket.send_json(
                {
                    "type": "candidate_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 2,
                        "silence_duration_ms": 500,
                    },
                }
            )
            self.assertEqual(
                websocket.receive_json()["type"],
                "smart_turn_started",
            )
            second_result = websocket.receive_json()
            self.assertTrue(
                second_result["payload"]["turn_complete"]
            )

            websocket.send_json(
                {
                    "type": "finalise_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 2,
                        "silence_duration_ms": 500,
                    },
                }
            )
            self.assertEqual(
                websocket.receive_json()["type"],
                "transcription_started",
            )
            transcription = self.receive_transcription(
                websocket,
                "segment-1",
            )

        self.assertTrue(
            transcription["payload"][
                "turn_completion_confirmed"
            ]
        )
        self.assertEqual(
            self.service.calls[0]["pcm_bytes"],
            first_pcm + continuation_pcm,
        )

    def test_speech_resume_invalidates_pending_prediction(
        self,
    ) -> None:
        smart_turn = BlockingSmartTurnService()
        client = self.make_client(
            self.service,
            smart_turn,
        )

        with client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-1")
            websocket.send_bytes(
                b"\x01\x00" * 8_000
            )
            websocket.send_json(
                {
                    "type": "candidate_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 1,
                        "silence_duration_ms": 500,
                    },
                }
            )
            self.assertEqual(
                websocket.receive_json()["type"],
                "smart_turn_started",
            )
            self.assertTrue(
                smart_turn.call_started.wait(timeout=2)
            )
            websocket.send_json(
                {
                    "type": "speech_resumed",
                    "payload": {
                        "segment_id": "segment-1",
                    },
                }
            )
            smart_turn.release_call.set()

            result = websocket.receive_json()
            self.assertEqual(
                result["type"],
                "smart_turn_result",
            )
            self.assertTrue(result["payload"]["stale"])

        self.assertEqual(self.service.calls, [])

    def test_forced_finalisation_bypasses_incomplete_candidate(
        self,
    ) -> None:
        smart_turn = FakeSmartTurnService([False])
        client = self.make_client(
            self.service,
            smart_turn,
        )

        with client.websocket_connect(
            "/api/audio/stream"
        ) as websocket:
            self.start_segment(websocket, "segment-1")
            websocket.send_bytes(
                b"\x01\x00" * 8_000
            )
            websocket.send_json(
                {
                    "type": "candidate_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 1,
                        "silence_duration_ms": 500,
                    },
                }
            )
            websocket.receive_json()
            websocket.receive_json()
            websocket.receive_json()

            websocket.send_json(
                {
                    "type": "finalise_segment",
                    "payload": {
                        "segment_id": "segment-1",
                        "candidate_id": 1,
                        "silence_duration_ms": 1_800,
                        "forced_finalisation": True,
                    },
                }
            )
            started = websocket.receive_json()
            self.assertTrue(
                started["payload"]["forced_finalisation"]
            )
            result = self.receive_transcription(
                websocket,
                "segment-1",
            )
            self.assertTrue(
                result["payload"][
                    "turn_completion_confirmed"
                ]
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
