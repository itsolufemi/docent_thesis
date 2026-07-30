import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    get_recent_conversation_history,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    ResolvedContext,
)
from conversation_core.services.model_route_parser import (  # noqa: E402
    ModelRouteStreamParser,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)
from conversation_core.api.routes_turn_buffer_stream import (  # noqa: E402
    build_stream_websocket_message,
)
from docent.services.docent_query_service import (  # noqa: E402
    docent_resolve_context_for_model_routing,
)


VALID_ROUTE_JSON = (
    '{"route_type":"response_request",'
    '"is_relevant":true,'
    '"should_ignore":false,'
    '"retrieval_required":true,'
    '"retrieved_context_used":true,'
    '"proposed_action":null,'
    '"confidence":0.98,'
    '"reason":"Artwork information requested."}'
)


def resolve_context(
    subject_reference,
    user_input,
    utterance_route=None,
):
    return ResolvedContext(
        context_source=(
            "vector_retrieved_chunks"
        ),
        subject_reference=subject_reference,
        debug_payload={
            "model_routing_retrieval_prefetched": (
                True
            ),
        },
    )


def build_prompt(
    user_input,
    dialogue_history,
    resolved_context,
    active_branch,
):
    return "model-routing prompt"


class ModelRouteStreamParserTest(
    unittest.TestCase
):
    def test_split_route_is_hidden_and_validated(
        self,
    ) -> None:
        parser = ModelRouteStreamParser()

        route, spoken = parser.consume(
            "<rou"
        )
        self.assertIsNone(route)
        self.assertEqual(spoken, "")

        route, spoken = parser.consume(
            "te>"
            + VALID_ROUTE_JSON
            + "</route>The Arab Tent "
        )

        self.assertIsNotNone(route)
        self.assertEqual(
            route.route_type,
            "response_request",
        )
        self.assertEqual(
            spoken,
            "The Arab Tent ",
        )

        route, spoken = parser.consume(
            "is an evocative painting."
        )
        self.assertIsNone(route)
        self.assertEqual(
            spoken,
            "is an evocative painting.",
        )

    def test_malformed_route_releases_answer(
        self,
    ) -> None:
        parser = ModelRouteStreamParser()

        route, spoken = parser.consume(
            "<route>{not valid}</route>"
            "A valid spoken answer."
        )

        self.assertIsNone(route)
        self.assertEqual(
            spoken,
            "A valid spoken answer.",
        )
        self.assertIsNotNone(
            parser.validation_error
        )

    def test_missing_route_fails_open(
        self,
    ) -> None:
        parser = ModelRouteStreamParser()

        route, spoken = parser.consume(
            "A normal spoken answer."
        )

        self.assertIsNone(route)
        self.assertEqual(
            spoken,
            "A normal spoken answer.",
        )


class ModelRoutingQueryEngineTest(
    unittest.TestCase
):
    def test_non_streamed_response_hides_route(
        self,
    ) -> None:
        raw_response = (
            "<route>"
            + VALID_ROUTE_JSON
            + "</route>"
            + "A spoken response."
        )
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            response_generator=(
                lambda prompt, conversation_id: (
                    raw_response
                )
            ),
            model_route_output_enabled=True,
        )

        result = engine.generate_response(
            text="Question",
            include_debug=True,
        )

        self.assertEqual(
            result.response,
            "A spoken response.",
        )
        self.assertTrue(
            result.debug.debug_payload[
                "model_route_valid"
            ]
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_route_event_precedes_spoken_content(
        self,
        stream_response,
    ) -> None:
        stream_response.return_value = iter(
            [
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "<route>"
                        + VALID_ROUTE_JSON[:70]
                    ),
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        VALID_ROUTE_JSON[70:]
                        + "</route>"
                        + "The Arab Tent "
                    ),
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="is richly decorated.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="raw model response",
                    done=True,
                ),
            ]
        )
        events = []
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            model_route_output_enabled=True,
        )

        result = (
            engine.generate_streaming_response(
                text=(
                    "Tell me about "
                    "The Arab Tent."
                ),
                include_debug=True,
                on_stream_event=events.append,
            )
        )

        self.assertEqual(
            result.response,
            (
                "The Arab Tent "
                "is richly decorated."
            ),
        )
        self.assertEqual(
            [
                event.event_type
                for event in events
            ],
            [
                "response_started",
                "route_assessment",
                "content_delta",
                "content_delta",
                "response_complete",
            ],
        )
        self.assertNotIn(
            "<route>",
            result.response,
        )
        self.assertTrue(
            result.debug.debug_payload[
                "model_route_valid"
            ]
        )

        history = (
            get_recent_conversation_history(
                conversation_id=(
                    result.conversation_id
                ),
            )
        )
        self.assertEqual(
            history[-1].content,
            result.response,
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_missing_route_keeps_spoken_answer(
        self,
        stream_response,
    ) -> None:
        stream_response.return_value = iter(
            [
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Hello there.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Hello there.",
                    done=True,
                ),
            ]
        )
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            model_route_output_enabled=True,
        )

        result = (
            engine.generate_streaming_response(
                text="Hello",
                include_debug=True,
            )
        )

        self.assertEqual(
            result.response,
            "Hello there.",
        )
        self.assertFalse(
            result.debug.debug_payload[
                "model_route_valid"
            ]
        )


class ModelRouteWebSocketMessageTest(
    unittest.TestCase
):
    def test_route_assessment_is_forwarded(
        self,
    ) -> None:
        route = json.loads(
            VALID_ROUTE_JSON
        )
        message = build_stream_websocket_message(
            request_id="request-1",
            event=LLMStreamEvent(
                event_type="route_assessment",
                route_assessment=route,
            ),
        )

        self.assertEqual(
            message["type"],
            "route_assessment",
        )
        self.assertEqual(
            message["payload"],
            route,
        )


class ClassifierFreeResolverTest(
    unittest.TestCase
):
    @patch(
        "docent.services.docent_query_service."
        "get_docent_retrieval_documents",
        return_value=[],
    )
    @patch(
        "docent.services.docent_query_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    @patch(
        "docent.services.docent_query_service."
        "route_utterance"
    )
    def test_model_routing_never_calls_classifier(
        self,
        route_utterance,
        retrieve_chunks,
        _get_documents,
    ) -> None:
        retrieval_result = Mock()
        retrieval_result.results = []
        retrieval_result.timings.model_dump.return_value = {}
        retrieve_chunks.return_value = (
            retrieval_result
        )

        resolved = (
            docent_resolve_context_for_model_routing(
                None,
                "Hello",
            )
        )

        route_utterance.assert_not_called()
        self.assertTrue(
            resolved.debug_payload[
                "model_routing_retrieval_prefetched"
            ]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
