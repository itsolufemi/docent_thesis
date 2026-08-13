import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from conversation_core.schemas.transcription_schemas import (  # noqa: E402
    TranscriptionResponse,
)
from models.moonshine.moonshine_transcription_service import (  # noqa: E402
    MoonshineStreamingTranscriptionService,
)


class MoonshinePcmFallbackTest(unittest.TestCase):
    def test_completed_pcm_uses_one_streaming_session(self) -> None:
        service = MoonshineStreamingTranscriptionService()
        session = Mock()
        expected = TranscriptionResponse(text="The Arab Tent")
        session.finish.return_value = expected
        service.create_session = Mock(return_value=session)
        audio = b"\x01\x00\x02\x00"

        result = service.transcribe_pcm16(
            audio,
            sample_rate=16_000,
            channels=1,
        )

        self.assertIs(result, expected)
        session.add_pcm16.assert_called_once_with(
            audio,
            sample_rate=16_000,
            channels=1,
        )
        session.finish.assert_called_once_with()

    def test_failed_pcm_fallback_cancels_session(self) -> None:
        service = MoonshineStreamingTranscriptionService()
        session = Mock()
        session.finish.side_effect = RuntimeError("failed")
        service.create_session = Mock(return_value=session)

        with self.assertRaisesRegex(RuntimeError, "failed"):
            service.transcribe_pcm16(
                b"\x00\x00",
                sample_rate=16_000,
            )

        session.cancel.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
