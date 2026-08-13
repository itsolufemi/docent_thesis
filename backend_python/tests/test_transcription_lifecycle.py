import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.transcription_factory import (  # noqa: E402
    TranscriptionStack,
    create_transcription_stack,
)


class TranscriptionStackTest(unittest.TestCase):
    def test_close_calls_optional_streaming_close(self) -> None:
        batch_service = Mock(provider_name="batch")
        streaming_service = Mock(provider_name="streaming")
        stack = TranscriptionStack(
            batch_service=batch_service,
            streaming_service=streaming_service,
        )

        stack.close()

        streaming_service.close.assert_called_once_with()

    def test_close_without_streaming_service_is_safe(self) -> None:
        stack = TranscriptionStack(
            batch_service=Mock(provider_name="batch")
        )

        stack.close()

    def test_qmul_live_fallback_is_moonshine(self) -> None:
        stack = create_transcription_stack("qmul_whisper")

        self.assertEqual(
            stack.streaming_service.provider_name,
            "qmul_whisper_large_v3",
        )
        self.assertEqual(
            stack.live_fallback_service.provider_name,
            "moonshine",
        )
        self.assertEqual(
            stack.batch_service.provider_name,
            "whisper",
        )


class QmulWhisperLifespanTest(unittest.TestCase):
    def test_qmul_provider_warms_and_closes(self) -> None:
        from server import lifespan

        app = FastAPI()

        async def enter_and_exit() -> None:
            transcription_stack = Mock(
                provider_name="qmul_whisper_large_v3"
            )
            transcription_stack.warm_up.return_value = 0.1

            with (
                patch(
                    "server.settings.transcription_backend",
                    "qmul_whisper",
                ),
                patch(
                    "server.settings."
                    "warm_up_qmul_whisper_on_startup",
                    True,
                ),
                patch(
                    "server.default_transcription_stack",
                    transcription_stack,
                ),
                patch(
                    "server.settings.warm_up_smart_turn_on_startup",
                    False,
                ),
                patch(
                    "server.settings.warm_up_retrieval_on_startup",
                    False,
                ),
                patch(
                    "server.settings.warm_up_llm_on_startup",
                    False,
                ),
                patch(
                    "server.settings.warm_up_tts_on_startup",
                    False,
                ),
                patch("server.default_tts_service.close"),
                patch("server.close_ollama_http_client"),
            ):
                async with lifespan(app):
                    pass

            transcription_stack.warm_up.assert_called_once_with()
            transcription_stack.close.assert_called_once_with()

        asyncio.run(enter_and_exit())


if __name__ == "__main__":
    unittest.main()
