import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("QMUL_JUPYTER_TOKEN", "test-token")

from conversation_core.schemas.transcription_schemas import (  # noqa: E402
    TranscriptionResponse,
)
from models.whisper_large_v3_qmul.qmul_whisper_transcription_service import (  # noqa: E402
    QmulWhisperStreamingSession,
    QmulWhisperStreamingTranscriptionService,
)


class QmulWhisperStreamingSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = Mock()
        self.session = QmulWhisperStreamingSession(
            service=self.service
        )

    def test_add_pcm16_forwards_valid_audio(self) -> None:
        audio = b"\x01\x00\x02\x00"

        self.session.add_pcm16(
            audio,
            sample_rate=16_000,
            channels=1,
        )

        self.service._send_audio.assert_called_once_with(audio)

    def test_add_pcm16_rejects_invalid_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "16000 Hz"):
            self.session.add_pcm16(
                b"\x00\x00",
                sample_rate=8_000,
            )

        with self.assertRaisesRegex(ValueError, "mono"):
            self.session.add_pcm16(
                b"\x00\x00",
                sample_rate=16_000,
                channels=2,
            )

        with self.assertRaisesRegex(ValueError, "even number"):
            self.session.add_pcm16(
                b"\x00",
                sample_rate=16_000,
            )

    def test_finish_releases_session(self) -> None:
        expected = TranscriptionResponse(text="The Arab Tent")
        self.service._finalize.return_value = expected

        result = self.session.finish()

        self.assertIs(result, expected)
        self.service._release_session.assert_called_once_with(
            self.session
        )

        with self.assertRaisesRegex(RuntimeError, "already finished"):
            self.session.finish()

    def test_cancel_resets_and_releases_session(self) -> None:
        self.session.cancel()

        self.service._reset_remote_buffer.assert_called_once_with()
        self.service._release_session.assert_called_once_with(
            self.session
        )


class QmulWhisperStreamingServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QmulWhisperStreamingTranscriptionService(
            websocket_url="wss://example.test/ws"
        )

    def test_audio_enqueue_is_non_blocking_and_fifo(self) -> None:
        first = b"\x01\x00"
        second = b"\x02\x00"

        self.service._send_audio(first)
        self.service._send_audio(second)

        self.assertEqual(
            self.service._command_queue.get_nowait(),
            (first, None),
        )
        self.assertEqual(
            self.service._command_queue.get_nowait(),
            (second, None),
        )

    def test_build_response_converts_remote_payload(self) -> None:
        result = self.service._build_response(
            {
                "text": " The Arab Tent ",
                "language": "en",
                "language_probability": 0.98,
                "audio_duration": 1.25,
                "segments": [
                    {
                        "start": 0.1,
                        "end": 1.2,
                        "text": " The Arab Tent ",
                    },
                    {
                        "start": 1.2,
                        "end": 1.25,
                        "text": " ",
                    },
                ],
            }
        )

        self.assertEqual(result.text, "The Arab Tent")
        self.assertEqual(result.duration_seconds, 1.25)
        self.assertEqual(len(result.segments), 1)
        self.assertEqual(
            result.segments[0].text,
            "The Arab Tent",
        )


if __name__ == "__main__":
    unittest.main()
