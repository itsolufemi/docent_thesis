import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from conversation_core.api.routes_turn_buffer_stream import (  # noqa: E402
    build_stream_websocket_message,
)
from conversation_core.memory.conversation_store import (  # noqa: E402
    get_recent_conversation_history,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    ResolvedContext,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)
from conversation_core.services.self_routing_parser import (  # noqa: E402
    SelfRoutingStreamParser,
)
from docent.services.docent_query_service import (  # noqa: E402
    build_candidate_subjects_from_chunks,
    docent_resolve_self_routing_context,
)


VALID_ROUTE = {
    "route_type": "response_request",
    "is_relevant": True,
    "candidate_subject": ["The Arab Tent"],
    "should_update_subject": True,
    "proposed_action": None,
    "confidence": 0.98,
    "reason": "...",
}

VALID_ROUTE_JSON = json.dumps(
    VALID_ROUTE,
    separators=(",", ":"),
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
            "self_routing_context_resolver": (
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
    return "self-routing prompt"


class SelfRoutingParserTest(
    unittest.TestCase
):
    def test_split_route_is_hidden(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        self.assertEqual(
            parser.consume("<rou"),
            "",
        )
        spoken = parser.consume(
            "te>"
            + VALID_ROUTE_JSON
            + "</route>The Arab Tent."
        )

        self.assertEqual(
            spoken,
            "The Arab Tent.",
        )
        self.assertEqual(
            parser.route,
            parser.route.model_validate(
                VALID_ROUTE
            ),
        )
        self.assertTrue(
            parser.route_complete
        )

    def test_malformed_route_releases_answer(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()
        spoken = parser.consume(
            "<route>{invalid}</route>"
            "A usable answer."
        )

        self.assertEqual(
            spoken,
            "A usable answer.",
        )
        self.assertIsNone(parser.route)
        self.assertIsNotNone(
            parser.validation_error
        )

    def test_missing_route_fails_open(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        self.assertEqual(
            parser.consume("Hello there."),
            "Hello there.",
        )
        self.assertIsNone(parser.route)


class CandidateSubjectTest(
    unittest.TestCase
):
    def test_chunks_are_deduplicated_by_parent(
        self,
    ) -> None:
        chunks = [
            SimpleNamespace(
                score=0.78,
                chunk=SimpleNamespace(
                    parent_document_id=(
                        "painting:581"
                    ),
                    title="The Arab Tent",
                ),
            ),
            SimpleNamespace(
                score=0.71,
                chunk=SimpleNamespace(
                    parent_document_id=(
                        "painting:581"
                    ),
                    title="The Arab Tent",
                ),
            ),
            SimpleNamespace(
                score=0.47,
                chunk=SimpleNamespace(
                    parent_document_id=(
                        "painting:118"
                    ),
                    title=(
                        "The Rising of the Sun"
                    ),
                ),
            ),
        ]

        candidates = (
            build_candidate_subjects_from_chunks(
                chunks
            )
        )

        self.assertEqual(
            [
                candidate["reference"]
                for candidate in candidates
            ],
            [
                "painting:581",
                "painting:118",
            ],
        )

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
    def test_resolver_never_calls_classifier(
        self,
        route_utterance,
        retrieve_chunks,
        _get_documents,
    ) -> None:
        result = Mock()
        result.results = []
        result.timings.model_dump.return_value = {}
        retrieve_chunks.return_value = result

        resolved = (
            docent_resolve_self_routing_context(
                None,
                "Hi",
            )
        )

        route_utterance.assert_not_called()
        self.assertTrue(
            resolved.debug_payload[
                "self_routing_context_resolver"
            ]
        )


class SelfRoutingQueryEngineTest(
    unittest.TestCase
):
    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_metadata_precedes_spoken_text(
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
                        + VALID_ROUTE_JSON[:80]
                    ),
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        VALID_ROUTE_JSON[80:]
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
                    text="raw response",
                    done=True,
                ),
            ]
        )
        events = []
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            self_routing_enabled=True,
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
            [
                event.event_type
                for event in events
                if event.event_type != "timing"
            ],
            [
                "response_started",
                "self_routing",
                "content_delta",
                "content_delta",
                "response_complete",
            ],
        )
        self.assertEqual(
            result.response,
            (
                "The Arab Tent "
                "is richly decorated."
            ),
        )
        self.assertTrue(
            result.debug.debug_payload[
                "self_routing_valid"
            ]
        )
        self.assertIsNotNone(
            result.debug.debug_payload[
                "timings"
            ]["self_routing_seconds"]
        )

        history = (
            get_recent_conversation_history(
                result.conversation_id
            )
        )
        self.assertNotIn(
            "<route>",
            history[-1].content,
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_missing_metadata_keeps_answer(
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
                    text="A spoken answer.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="A spoken answer.",
                    done=True,
                ),
            ]
        )
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            self_routing_enabled=True,
        )

        result = (
            engine.generate_streaming_response(
                text="Question",
                include_debug=True,
            )
        )

        self.assertEqual(
            result.response,
            "A spoken answer.",
        )
        self.assertFalse(
            result.debug.debug_payload[
                "self_routing_valid"
            ]
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_tool_events_follow_metadata(
        self,
        stream_response,
    ) -> None:
        stream_response.return_value = iter(
            [
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="tool_call",
                    tool_calls=[
                        {
                            "name": (
                                "create_conversation_branch"
                            ),
                            "arguments": {},
                        }
                    ],
                ),
                LLMStreamEvent(
                    event_type="tool_result",
                    tool_name=(
                        "create_conversation_branch"
                    ),
                    tool_result={
                        "success": True,
                    },
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "<route>"
                        + VALID_ROUTE_JSON
                        + "</route>Tour started."
                    ),
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Tour started.",
                    done=True,
                ),
            ]
        )
        events = []
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            self_routing_enabled=True,
        )

        engine.generate_streaming_response(
            text="Start a tour.",
            on_stream_event=events.append,
        )

        self.assertEqual(
            [
                event.event_type
                for event in events
                if event.event_type != "timing"
            ],
            [
                "response_started",
                "self_routing",
                "tool_call",
                "tool_result",
                "content_delta",
                "response_complete",
            ],
        )


class SelfRoutingWebSocketTest(
    unittest.TestCase
):
    def test_event_is_forwarded(
        self,
    ) -> None:
        message = build_stream_websocket_message(
            request_id="request-1",
            event=LLMStreamEvent(
                event_type="self_routing",
                route_assessment=VALID_ROUTE,
            ),
        )

        self.assertEqual(
            message["type"],
            "self_routing",
        )
        self.assertTrue(
            message["payload"]["valid"]
        )
        self.assertEqual(
            message["payload"]["assessment"],
            VALID_ROUTE,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
