import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.api.routes_conversation import (
    create_conversation_router,
)
from conversation_core.memory.conversation_store import (
    conversations,
    create_conversation,
    get_active_branch,
)
from conversation_core.schemas.introduction_schemas import (
    IntroductionDefinition,
)
from conversation_core.services.query_service import (
    QueryEngine,
)
from docent.services.introduction_service import (
    build_docent_introduction,
)


class FailingResolver:
    def __call__(self, *args, **kwargs):
        raise AssertionError(
            "Introduction generation must not resolve context."
        )


class FailingPromptBuilder:
    def __call__(self, *args, **kwargs):
        raise AssertionError(
            "Introduction generation must not build a query prompt."
        )


def build_definition() -> IntroductionDefinition:
    return IntroductionDefinition(
        prompt="Introduce yourself as Docent.",
        fallback_text="Hello, I'm Docent.",
    )


class IntroductionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()

    def build_engine(
        self,
        *,
        provider=build_definition,
        generator=None,
    ) -> QueryEngine:
        return QueryEngine(
            subject_resolver=FailingResolver(),
            prompt_builder=FailingPromptBuilder(),
            introduction_provider=provider,
            introduction_response_generator=(
                generator
                or (
                    lambda prompt: (
                        "Hello, I'm Docent. "
                        "How are you today?"
                    )
                )
            ),
        )

    def test_no_provider_returns_no_introduction(
        self,
    ) -> None:
        state = create_conversation()
        engine = self.build_engine(
            provider=None,
        )

        self.assertIsNone(
            engine.generate_introduction(
                conversation_id=state.conversation_id
            )
        )
        self.assertEqual(
            state.dialogue_history,
            [],
        )

    def test_provider_generates_and_stores_assistant_turn(
        self,
    ) -> None:
        state = create_conversation()
        generator = Mock(
            return_value=(
                "Hello, I'm Docent. How are you today?"
            )
        )
        engine = self.build_engine(
            generator=generator
        )

        result = engine.generate_introduction(
            conversation_id=state.conversation_id
        )

        self.assertEqual(
            result,
            "Hello, I'm Docent. How are you today?",
        )
        generator.assert_called_once_with(
            "Introduce yourself as Docent."
        )
        self.assertEqual(
            state.dialogue_history[0].role,
            "assistant",
        )
        self.assertEqual(
            state.dialogue_history[0].content,
            result,
        )

    def test_llm_failure_returns_fallback(
        self,
    ) -> None:
        state = create_conversation()

        def fail(_prompt: str) -> str:
            raise RuntimeError("LLM unavailable")

        engine = self.build_engine(generator=fail)

        self.assertEqual(
            engine.generate_introduction(
                conversation_id=state.conversation_id
            ),
            "Hello, I'm Docent.",
        )

    def test_repeated_endpoint_request_generates_once(
        self,
    ) -> None:
        generator = Mock(
            return_value="Hello, I'm Docent."
        )
        engine = self.build_engine(
            generator=generator
        )
        app = FastAPI()
        app.include_router(
            create_conversation_router(engine)
        )

        with TestClient(app) as client:
            first = client.post(
                "/api/conversations/current/introduction"
            )
            second = client.post(
                "/api/conversations/current/introduction"
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["generated"])
        self.assertFalse(second.json()["generated"])
        self.assertEqual(
            first.json()["conversation_id"],
            second.json()["conversation_id"],
        )
        generator.assert_called_once()

    def test_introduction_does_not_change_subjects_or_add_route(
        self,
    ) -> None:
        state = create_conversation()
        engine = self.build_engine()
        branch = get_active_branch(
            state.conversation_id
        )

        result = engine.generate_introduction(
            conversation_id=state.conversation_id
        )

        self.assertIsNotNone(branch)
        self.assertEqual(branch.current_subjects, [])
        self.assertNotIn("<route>", result)

    def test_docent_definition_identifies_docent_without_route(
        self,
    ) -> None:
        definition = build_docent_introduction()

        self.assertIn("Docent", definition.prompt)
        self.assertIn(
            "Docent",
            definition.fallback_text,
        )
        self.assertNotIn(
            "<route>",
            definition.prompt,
        )


class LifespanTest(unittest.TestCase):
    def test_warm_up_failure_does_not_prevent_startup(
        self,
    ) -> None:
        from server import lifespan

        app = FastAPI()

        async def enter_and_exit() -> None:
            with (
                patch(
                    "server.settings.transcription_backend",
                    "whisper",
                ),
                patch(
                    "server.settings."
                    "warm_up_whisper_on_startup",
                    True,
                ),
                patch(
                    "server.default_transcription_service."
                    "warm_up",
                    side_effect=RuntimeError(
                        "warm-up failed"
                    ),
                ),
                patch(
                    "server.settings."
                    "warm_up_smart_turn_on_startup",
                    False,
                ),
                patch(
                    "server.settings."
                    "warm_up_retrieval_on_startup",
                    False,
                ),
                patch(
                    "server.settings."
                    "warm_up_llm_on_startup",
                    False,
                ),
                patch(
                    "server.settings."
                    "warm_up_tts_on_startup",
                    False,
                ),
                patch(
                    "server.close_ollama_http_client"
                ) as close_client,
            ):
                async with lifespan(app):
                    pass

            close_client.assert_called_once_with()

        asyncio.run(enter_and_exit())


if __name__ == "__main__":
    unittest.main(verbosity=2)
