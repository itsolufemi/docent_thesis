import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.api.routes_transcription import (
    create_transcription_router,
)
from conversation_core.schemas.transcription_schemas import (
    TranscriptionResponse,
)


class FakeTranscriptionService:
    def __init__(self) -> None:
        self.received_path: Path | None = None
        self.path_existed_during_call = False

    def transcribe_file(self, audio_path) -> TranscriptionResponse:
        self.received_path = Path(audio_path)
        self.path_existed_during_call = self.received_path.exists()

        return TranscriptionResponse(
            text="Tell me about The Arab Tent.",
            language="en",
            language_probability=0.99,
            duration_seconds=2.5,
        )


class TranscriptionRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeTranscriptionService()
        app = FastAPI()
        app.include_router(
            create_transcription_router(self.service)
        )
        self.client = TestClient(app)

    def test_upload_is_transcribed_and_temporary_file_is_removed(self) -> None:
        response = self.client.post(
            "/api/transcription",
            files={
                "audio": (
                    "utterance.wav",
                    b"fake wav bytes",
                    "audio/wav",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["text"],
            "Tell me about The Arab Tent.",
        )
        self.assertTrue(self.service.path_existed_during_call)
        self.assertIsNotNone(self.service.received_path)
        self.assertFalse(self.service.received_path.exists())

    def test_unsupported_content_type_is_rejected(self) -> None:
        response = self.client.post(
            "/api/transcription",
            files={
                "audio": (
                    "notes.txt",
                    b"not audio",
                    "text/plain",
                ),
            },
        )

        self.assertEqual(response.status_code, 415)

    def test_empty_audio_is_rejected(self) -> None:
        response = self.client.post(
            "/api/transcription",
            files={
                "audio": (
                    "empty.wav",
                    b"",
                    "audio/wav",
                ),
            },
        )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
