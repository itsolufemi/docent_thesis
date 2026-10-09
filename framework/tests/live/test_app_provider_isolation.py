import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FRAMEWORK_ROOT.parent

for import_root in (REPOSITORY_ROOT, FRAMEWORK_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app_factory import create_framework_app
from config import settings
from core_engine.default_profile_definition import (
    default_classifier_profile,
)
from core_engine.services.query_service import default_query_engine
from models.transcription_factory import (
    TranscriptionStack,
    create_transcription_stack,
)
from models.tts_factory import create_tts_service


class FakeBatchTranscriptionService:
    provider_name = "fake_batch"


class FakeStreamingTranscriptionService:
    provider_name = "fake_streaming"

    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class FailingClosableTranscriptionService:
    provider_name = "failing"

    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1
        raise RuntimeError("close failed")


class FakeTextToSpeechService:
    provider_name = "fake_tts"
    default_voice_name = "test"
    default_language_code = "en-GB"
    sample_rate = 24_000
    recommended_prebuffer_ms = 0

    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


async def run_lifespan(app) -> None:
    async with app.router.lifespan_context(app):
        pass


class ApplicationProviderIsolationTests(unittest.TestCase):
    def create_test_app(
        self,
        *,
        transcription_stack: TranscriptionStack,
        tts_service: FakeTextToSpeechService,
        own_providers: bool | None = None,
    ):
        return create_framework_app(
            title="Provider isolation test",
            query_engine=default_query_engine,
            domain_profile=default_classifier_profile,
            transcription_stack=transcription_stack,
            tts_service=tts_service,
            close_transcription_stack_on_shutdown=own_providers,
            close_tts_service_on_shutdown=own_providers,
            warm_up_transcription_on_startup=False,
            warm_up_tts_on_startup=False,
        )

    def test_default_factories_return_fresh_providers(self) -> None:
        first_stack = create_transcription_stack("whisper")
        second_stack = create_transcription_stack("whisper")
        first_tts = create_tts_service("kyutai_pocket")
        second_tts = create_tts_service("kyutai_pocket")

        self.assertIsNot(first_stack, second_stack)
        self.assertIsNot(
            first_stack.batch_service,
            second_stack.batch_service,
        )
        self.assertIsNot(first_tts, second_tts)

    def test_framework_apps_receive_independent_defaults(self) -> None:
        with (
            patch.object(settings, "transcription_backend", "whisper"),
            patch.object(settings, "tts_backend", "kyutai_pocket"),
            patch.object(settings, "smart_turn_enabled", False),
        ):
            first_app = create_framework_app(
                title="First app",
                query_engine=default_query_engine,
                domain_profile=default_classifier_profile,
                warm_up_transcription_on_startup=False,
                warm_up_tts_on_startup=False,
            )
            second_app = create_framework_app(
                title="Second app",
                query_engine=default_query_engine,
                domain_profile=default_classifier_profile,
                warm_up_transcription_on_startup=False,
                warm_up_tts_on_startup=False,
            )

        self.assertIsNot(
            first_app.state.transcription_stack,
            second_app.state.transcription_stack,
        )
        self.assertIsNot(
            first_app.state.transcription_stack.batch_service,
            second_app.state.transcription_stack.batch_service,
        )
        self.assertIsNot(
            first_app.state.tts_service,
            second_app.state.tts_service,
        )
        self.assertTrue(first_app.state.owns_transcription_stack)
        self.assertTrue(first_app.state.owns_tts_service)

    def test_injected_shared_providers_are_not_closed_by_default(self) -> None:
        streaming_service = FakeStreamingTranscriptionService()
        transcription_stack = TranscriptionStack(
            batch_service=FakeBatchTranscriptionService(),
            streaming_service=streaming_service,
        )
        tts_service = FakeTextToSpeechService()

        with (
            patch.object(settings, "smart_turn_enabled", False),
            patch.object(settings, "warm_up_llm_on_startup", False),
        ):
            first_app = self.create_test_app(
                transcription_stack=transcription_stack,
                tts_service=tts_service,
            )
            second_app = self.create_test_app(
                transcription_stack=transcription_stack,
                tts_service=tts_service,
            )
            asyncio.run(run_lifespan(first_app))
            asyncio.run(run_lifespan(second_app))

        self.assertFalse(first_app.state.owns_transcription_stack)
        self.assertFalse(first_app.state.owns_tts_service)
        self.assertEqual(streaming_service.close_count, 0)
        self.assertEqual(tts_service.close_count, 0)

    def test_injected_provider_ownership_can_be_transferred(self) -> None:
        streaming_service = FakeStreamingTranscriptionService()
        transcription_stack = TranscriptionStack(
            batch_service=FakeBatchTranscriptionService(),
            streaming_service=streaming_service,
        )
        tts_service = FakeTextToSpeechService()

        with (
            patch.object(settings, "smart_turn_enabled", False),
            patch.object(settings, "warm_up_llm_on_startup", False),
        ):
            app = self.create_test_app(
                transcription_stack=transcription_stack,
                tts_service=tts_service,
                own_providers=True,
            )
            asyncio.run(run_lifespan(app))

        self.assertTrue(app.state.owns_transcription_stack)
        self.assertTrue(app.state.owns_tts_service)
        self.assertEqual(streaming_service.close_count, 1)
        self.assertEqual(tts_service.close_count, 1)


class TranscriptionStackCleanupTests(unittest.TestCase):
    def test_all_distinct_closable_services_are_closed(self) -> None:
        batch_service = FakeStreamingTranscriptionService()
        streaming_service = FakeStreamingTranscriptionService()
        fallback_service = FakeStreamingTranscriptionService()
        stack = TranscriptionStack(
            batch_service=batch_service,
            streaming_service=streaming_service,
            fallback_service=fallback_service,
        )

        stack.close()

        self.assertEqual(batch_service.close_count, 1)
        self.assertEqual(streaming_service.close_count, 1)
        self.assertEqual(fallback_service.close_count, 1)

    def test_service_used_in_multiple_roles_is_closed_once(self) -> None:
        shared_service = FakeStreamingTranscriptionService()
        stack = TranscriptionStack(
            batch_service=shared_service,
            streaming_service=shared_service,
            fallback_service=shared_service,
        )

        stack.close()

        self.assertEqual(shared_service.close_count, 1)

    def test_cleanup_continues_after_a_service_fails(self) -> None:
        failing_service = FailingClosableTranscriptionService()
        remaining_service = FakeStreamingTranscriptionService()
        stack = TranscriptionStack(
            batch_service=remaining_service,
            streaming_service=failing_service,
        )

        with self.assertRaises(ExceptionGroup) as raised:
            stack.close()

        self.assertEqual(failing_service.close_count, 1)
        self.assertEqual(remaining_service.close_count, 1)
        self.assertEqual(len(raised.exception.exceptions), 1)


if __name__ == "__main__":
    unittest.main()
