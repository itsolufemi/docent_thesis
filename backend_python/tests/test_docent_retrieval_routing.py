import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.schemas.utterance_route_schemas import UtteranceRoute
from conversation_core.schemas.query_schemas import ResolvedContext
from conversation_core.services.utterance_router_service import (
    normalise_boolean,
)
from docent.services.docent_query_service import (
    docent_build_prompt_from_context,
    docent_resolve_context,
)


def utterance_route(
    *,
    route_type: str,
    requires_retrieval: bool,
    proposed_action: str | None = None,
    candidate_subjects: list[str] | None = None,
) -> UtteranceRoute:
    return UtteranceRoute(
        route_type=route_type,
        requires_retrieval=requires_retrieval,
        proposed_action=proposed_action,
        candidate_subjects=candidate_subjects or [],
        is_relevant=True,
        should_ignore=False,
        confidence=0.95,
        reason="Test classification.",
    )


def empty_vector_result():
    return SimpleNamespace(
        results=[],
        timings=SimpleNamespace(
            model_dump=lambda: {},
        ),
    )


class BooleanNormalisationTest(unittest.TestCase):
    def test_string_booleans_are_normalised(self) -> None:
        self.assertTrue(normalise_boolean("true"))
        self.assertTrue(normalise_boolean(" TRUE "))
        self.assertFalse(normalise_boolean("false"))
        self.assertFalse(normalise_boolean(" FALSE "))
        self.assertFalse(normalise_boolean("not-a-boolean"))


class DocentRetrievalRoutingTest(unittest.TestCase):
    def resolve_with_route(
        self,
        route: UtteranceRoute,
        user_input: str,
    ):
        with (
            patch(
                "docent.services.docent_query_service.route_utterance",
                return_value=route,
            ),
            patch(
                "docent.services.docent_query_service."
                "retrieve_docent_chunks_by_vector_similarity",
                return_value=empty_vector_result(),
            ) as vector_retrieval,
            patch(
                "docent.services.docent_query_service."
                "get_docent_retrieval_documents",
                return_value=[],
            ),
            patch(
                "docent.services.docent_query_service."
                "retrieve_documents_by_keyword",
                return_value=[],
            ) as keyword_retrieval,
        ):
            context = docent_resolve_context(
                subject_reference=None,
                user_input=user_input,
            )

        return context, vector_retrieval, keyword_retrieval

    def test_preclassified_route_is_reused(self) -> None:
        route = utterance_route(
            route_type="response_request",
            requires_retrieval=False,
        )

        with patch(
            "docent.services.docent_query_service.route_utterance",
        ) as classify:
            context = docent_resolve_context(
                subject_reference=None,
                user_input="Hello.",
                utterance_route=route,
            )

        classify.assert_not_called()
        self.assertEqual(
            context.prompt_payload["route_type"],
            "response_request",
        )

    def test_greeting_skips_retrieval(self) -> None:
        route = utterance_route(
            route_type="response_request",
            requires_retrieval=False,
            candidate_subjects=["introductions"],
        )

        context, vector_retrieval, keyword_retrieval = (
            self.resolve_with_route(route, "Hello, how are you?")
        )

        self.assertEqual(
            context.context_source,
            "utterance_without_retrieval",
        )
        self.assertEqual(
            context.prompt_payload["candidate_subjects"],
            ["introductions"],
        )
        vector_retrieval.assert_not_called()
        keyword_retrieval.assert_not_called()

    def test_artwork_request_runs_retrieval(self) -> None:
        route = utterance_route(
            route_type="response_request",
            requires_retrieval=True,
            candidate_subjects=["The Arab Tent"],
        )

        context, vector_retrieval, _ = self.resolve_with_route(
            route,
            "Tell me about The Arab Tent.",
        )

        vector_retrieval.assert_called_once()
        self.assertEqual(
            vector_retrieval.call_args.kwargs["query"],
            "Tell me about The Arab Tent.",
        )
        self.assertTrue(context.prompt_payload["requires_retrieval"])
        self.assertEqual(
            context.prompt_payload["candidate_subjects"],
            ["The Arab Tent"],
        )

    def test_create_tour_retrieves_and_preserves_action(self) -> None:
        route = utterance_route(
            route_type="call_to_action",
            requires_retrieval=True,
            proposed_action="create_bounded_branch",
            candidate_subjects=["highlights tour"],
        )

        context, vector_retrieval, _ = self.resolve_with_route(
            route,
            "Give me a highlights tour.",
        )

        vector_retrieval.assert_called_once()
        self.assertEqual(
            vector_retrieval.call_args.kwargs["query"],
            "Give me a highlights tour.",
        )
        self.assertNotEqual(
            context.context_source,
            "utterance_without_retrieval",
        )
        self.assertEqual(
            context.prompt_payload["proposed_action"],
            "create_bounded_branch",
        )

    def test_close_tour_skips_retrieval_and_preserves_action(self) -> None:
        route = utterance_route(
            route_type="call_to_action",
            requires_retrieval=False,
            proposed_action="close_bounded_branch",
        )

        context, vector_retrieval, keyword_retrieval = (
            self.resolve_with_route(route, "Stop the tour.")
        )

        self.assertEqual(
            context.context_source,
            "utterance_without_retrieval",
        )
        self.assertEqual(
            context.prompt_payload["proposed_action"],
            "close_bounded_branch",
        )
        self.assertTrue(
            context.debug_payload["action_execution_available"]
        )
        vector_retrieval.assert_not_called()
        keyword_retrieval.assert_not_called()


class DocentPromptClassificationTest(unittest.TestCase):
    @patch(
        "docent.services.docent_query_service.docent_build_prompt",
        return_value="built prompt",
    )
    def test_retrieval_prompt_preserves_action_metadata(
        self,
        build_prompt,
    ) -> None:
        context = ResolvedContext(
            context_source="no_external_context",
            prompt_payload={
                "route_type": "call_to_action",
                "requires_retrieval": True,
                "proposed_action": "create_bounded_branch",
                "candidate_subjects": ["highlights tour"],
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": [],
            },
        )

        result = docent_build_prompt_from_context(
            user_input="Give me a highlights tour.",
            dialogue_history=[],
            resolved_context=context,
            active_branch=None,
        )

        self.assertEqual(result, "built prompt")
        wrapped_input = build_prompt.call_args.kwargs["user_input"]
        self.assertIn("call_to_action", wrapped_input)
        self.assertIn("create_bounded_branch", wrapped_input)
        self.assertIn("highlights tour", wrapped_input)
        self.assertIn("current_subjects empty", wrapped_input)

    def test_no_retrieval_prompt_preserves_close_action(self) -> None:
        context = ResolvedContext(
            context_source="utterance_without_retrieval",
            prompt_payload={
                "route_type": "call_to_action",
                "requires_retrieval": False,
                "proposed_action": "close_bounded_branch",
                "candidate_subjects": [],
                "route_handled_without_retrieval": True,
                "route_message": "No retrieval required.",
            },
        )

        prompt = docent_build_prompt_from_context(
            user_input="Stop the tour.",
            dialogue_history=[],
            resolved_context=context,
            active_branch=None,
        )

        self.assertIn("call_to_action", prompt)
        self.assertIn("close_bounded_branch", prompt)
        self.assertIn("No retrieval required.", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
