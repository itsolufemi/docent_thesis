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
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    DialogueTurn,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    ResolvedContext,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
    derive_retrieved_subject_state,
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
    "candidate_subjects": ["The Arab Tent"],
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
        prompt_payload={
            "candidate_subjects": [
                {
                    "reference": "painting:581",
                    "label": "The Arab Tent",
                    "score": 0.92,
                }
            ],
        },
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
    def test_split_footer_is_hidden(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        self.assertEqual(
            parser.consume(
                "The Arab Tent is richly "
            ),
            "The Arab Tent is richly ",
        )
        self.assertEqual(
            parser.consume(
                "decorated.\n<rou"
            ),
            "decorated.\n",
        )
        spoken = parser.consume(
            "te>"
            + VALID_ROUTE_JSON
            + "</route>"
        )

        self.assertEqual(
            spoken,
            "",
        )
        self.assertIsNotNone(
            parser.route
        )
        self.assertEqual(
            parser.route.candidate_subjects,
            ["The Arab Tent"],
        )
        self.assertTrue(
            parser.route_complete
        )

    def test_malformed_route_releases_answer(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()
        spoken = parser.consume(
            "A usable answer."
            "<route>{invalid}</route>"
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
        self.assertEqual(parser.finish(), "")
        self.assertIsNone(parser.route)
        self.assertEqual(
            parser.validation_error,
            (
                "The response ended without a "
                "self-routing footer."
            ),
        )

    def test_ignored_turn_contains_only_footer(
        self,
    ) -> None:
        route = {
            "route_type": "noise",
            "is_relevant": False,
            "candidate_subjects": [],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.99,
            "reason": "The input was noise.",
        }

        parser = SelfRoutingStreamParser()

        spoken = parser.consume(
            "<route>"
            + json.dumps(route)
            + "</route>"
        )

        self.assertEqual(spoken, "")
        self.assertIsNotNone(parser.route)
        self.assertFalse(parser.route.is_relevant)

    def test_text_after_footer_is_not_released(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        spoken = parser.consume(
            "Answer."
            "<route>"
            + VALID_ROUTE_JSON
            + "</route>"
            "This must not be spoken."
        )

        self.assertEqual(spoken, "Answer.")
        self.assertIsNotNone(
            parser.validation_error
        )

    def test_whitespace_after_footer_is_ignored(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        parser.consume(
            "Answer.<route>"
            + VALID_ROUTE_JSON
            + "</route>"
        )

        self.assertEqual(parser.consume("\n"), "")
        self.assertIsNone(parser.validation_error)

    def test_partial_footer_at_stream_end_is_not_released(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        self.assertEqual(
            parser.consume("Answer.<rou"),
            "Answer.",
        )
        self.assertEqual(parser.finish(), "")
        self.assertEqual(
            parser.validation_error,
            (
                "The self-routing footer was not "
                "closed."
            ),
        )

    def test_cancel_discards_partial_footer_without_error(
        self,
    ) -> None:
        parser = SelfRoutingStreamParser()

        self.assertEqual(
            parser.consume("Partial answer.<rou"),
            "Partial answer.",
        )

        parser.cancel()

        self.assertIsNone(parser.route)
        self.assertIsNone(parser.validation_error)
        self.assertFalse(parser.route_just_completed)

    def test_old_redundant_fields_are_rejected(
        self,
    ) -> None:
        route = {
            "route_type": "response_request",
            "is_relevant": True,
            "should_ignore": False,
            "retrieval_available": True,
            "retrieval_used": True,
            "candidate_subject_reference": (
                "painting:581"
            ),
            "candidate_subjects": [
                "The Arab Tent",
            ],
            "should_update_subject": True,
            "proposed_action": None,
            "confidence": 0.98,
            "reason": "Old schema.",
        }

        parser = SelfRoutingStreamParser()

        spoken = parser.consume(
            "A usable answer."
            "<route>"
            + json.dumps(route)
            + "</route>"
        )

        self.assertEqual(
            spoken,
            "A usable answer.",
        )
        self.assertIsNone(parser.route)
        self.assertIsNotNone(
            parser.validation_error
        )


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

    def test_multiple_candidate_subjects_are_parsed(
        self,
    ) -> None:
        route = {
            "route_type": "response_request",
            "is_relevant": True,
            "candidate_subjects": [
                "The Swing",
                "The Arab Tent",
            ],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.97,
            "reason": (
                "The user requested a comparison "
                "between two paintings."
            ),
        }

        parser = SelfRoutingStreamParser()

        spoken = parser.consume(
            "The two paintings differ considerably."
            "<route>"
            + json.dumps(route)
            + "</route>"
        )

        self.assertEqual(
            spoken,
            "The two paintings differ considerably.",
        )
        self.assertIsNotNone(parser.route)
        self.assertEqual(
            parser.route.candidate_subjects,
            [
                "The Swing",
                "The Arab Tent",
            ],
        )

    def test_empty_candidate_subjects_are_valid(
        self,
    ) -> None:
        route = {
            "route_type": "response_request",
            "is_relevant": True,
            "candidate_subjects": [],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.94,
            "reason": (
                "The utterance is a greeting "
                "with no specific subject."
            ),
        }

        parser = SelfRoutingStreamParser()

        parser.consume(
            "Hello."
            "<route>"
            + json.dumps(route)
            + "</route>"
        )

        self.assertIsNotNone(parser.route)
        self.assertEqual(
            parser.route.candidate_subjects,
            [],
        )


class SelfRoutingQueryEngineTest(
    unittest.TestCase
):
    def test_non_streaming_stores_retrieved_subject_state(
        self,
    ) -> None:
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            response_generator=(
                lambda _prompt, _conversation_id: (
                    "The Arab Tent is an "
                    "orientalist painting."
                    "<route>"
                    + VALID_ROUTE_JSON
                    + "</route>"
                )
            ),
            self_routing_enabled=True,
        )

        result = engine.generate_response(
            text="Tell me about The Arab Tent.",
        )

        history = get_recent_conversation_history(
            result.conversation_id
        )

        self.assertEqual(len(history), 2)

        for turn in history:
            self.assertIsNone(
                turn.previous_subject
            )
            self.assertEqual(
                turn.current_subject,
                "The Arab Tent",
            )
            self.assertEqual(
                turn.current_subject_reference,
                "painting:581",
            )

    def test_retrieved_subject_records_previous_subject(
        self,
    ) -> None:
        first_engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            response_generator=(
                lambda _prompt, _conversation_id: (
                    "First answer."
                    "<route>"
                    + VALID_ROUTE_JSON
                    + "</route>"
                )
            ),
            self_routing_enabled=True,
        )

        first_result = first_engine.generate_response(
            text="Tell me about The Arab Tent.",
        )

        second_route = {
            **VALID_ROUTE,
            "candidate_subjects": [
                "The Laughing Cavalier"
            ],
        }

        def second_resolver(
            subject_reference,
            user_input,
            utterance_route=None,
        ):
            return ResolvedContext(
                context_source=(
                    "vector_retrieved_chunks"
                ),
                prompt_payload={
                    "candidate_subjects": [
                        {
                            "reference": (
                                "painting:84"
                            ),
                            "label": (
                                "The Laughing Cavalier"
                            ),
                            "score": 0.95,
                        }
                    ],
                },
            )

        second_engine = QueryEngine(
            subject_resolver=second_resolver,
            prompt_builder=build_prompt,
            response_generator=(
                lambda _prompt, _conversation_id: (
                    "Second answer."
                    "<route>"
                    + json.dumps(second_route)
                    + "</route>"
                )
            ),
            self_routing_enabled=True,
        )

        second_engine.generate_response(
            text=(
                "Now tell me about "
                "The Laughing Cavalier."
            ),
            conversation_id=(
                first_result.conversation_id
            ),
        )

        history = get_recent_conversation_history(
            first_result.conversation_id
        )

        user_turn = history[-2]
        assistant_turn = history[-1]

        for turn in (
            user_turn,
            assistant_turn,
        ):
            self.assertEqual(
                turn.previous_subject,
                "The Arab Tent",
            )
            self.assertEqual(
                turn.current_subject,
                "The Laughing Cavalier",
            )
            self.assertEqual(
                turn.current_subject_reference,
                "painting:84",
            )

    def test_no_retrieved_subject_retains_existing_state(
        self,
    ) -> None:
        dialogue_history = [
            DialogueTurn(
                role="assistant",
                content="Previous answer.",
                current_subject="The Arab Tent",
                current_subject_reference=(
                    "painting:581"
                ),
            )
        ]

        resolved_context = ResolvedContext(
            context_source="no_external_context",
            prompt_payload={
                "candidate_subjects": [],
            },
        )

        state = derive_retrieved_subject_state(
            dialogue_history,
            resolved_context,
        )

        self.assertEqual(
            state,
            (
                "The Arab Tent",
                "The Arab Tent",
                "painting:581",
            ),
        )

    def test_non_streaming_footer_is_removed(
        self,
    ) -> None:
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            response_generator=(
                lambda _prompt, _conversation_id: (
                    "A usable answer."
                    "<route>"
                    + VALID_ROUTE_JSON
                    + "</route>"
                )
            ),
            self_routing_enabled=True,
        )

        result = engine.generate_response(
            text="Question",
            include_debug=True,
        )

        self.assertEqual(
            result.response,
            "A usable answer.",
        )
        self.assertTrue(
            result.debug.debug_payload[
                "self_routing_valid"
            ]
        )
        self.assertTrue(
            result.debug.debug_payload[
                "self_routing_consistent"
            ]
        )

    def test_non_streaming_ignored_turn_stores_no_assistant(
        self,
    ) -> None:
        route = {
            "route_type": "noise",
            "is_relevant": False,
            "candidate_subjects": [],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.99,
            "reason": "The input was noise.",
        }
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            response_generator=(
                lambda _prompt, _conversation_id: (
                    "<route>"
                    + json.dumps(route)
                    + "</route>"
                )
            ),
            self_routing_enabled=True,
        )

        result = engine.generate_response(
            text="[background noise]",
            include_debug=True,
        )

        self.assertEqual(result.response, "")
        history = get_recent_conversation_history(
            result.conversation_id
        )
        self.assertEqual(
            [turn.role for turn in history],
            ["user"],
        )

    def test_non_streaming_irrelevant_text_records_error(
        self,
    ) -> None:
        route = {
            "route_type": "noise",
            "is_relevant": False,
            "candidate_subjects": [],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.99,
            "reason": "The input was noise.",
        }
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            response_generator=(
                lambda _prompt, _conversation_id: (
                    "Sorry?"
                    "<route>"
                    + json.dumps(route)
                    + "</route>"
                )
            ),
            self_routing_enabled=True,
        )

        result = engine.generate_response(
            text="[background noise]",
            include_debug=True,
        )

        self.assertEqual(result.response, "Sorry?")
        self.assertFalse(
            result.debug.debug_payload[
                "self_routing_consistent"
            ]
        )
        self.assertIn(
            "declaring is_relevant=false",
            result.debug.debug_payload[
                "self_routing_validation_error"
            ],
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_spoken_text_precedes_footer_metadata(
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
                    text="The Arab Tent ",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "is richly decorated.\n<rou"
                    ),
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "te>"
                        + VALID_ROUTE_JSON
                        + "</route>"
                    ),
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
                "content_delta",
                "content_delta",
                "self_routing",
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
            ]["self_routing_footer_seconds"]
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
        for turn in history:
            self.assertIsNone(
                turn.previous_subject
            )
            self.assertEqual(
                turn.current_subject,
                "The Arab Tent",
            )
            self.assertEqual(
                turn.current_subject_reference,
                "painting:581",
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
        self.assertEqual(
            result.debug.debug_payload[
                "self_routing_validation_error"
            ],
            (
                "The response ended without a "
                "self-routing footer."
            ),
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_irrelevant_route_with_spoken_text_is_inconsistent(
        self,
        stream_response,
    ) -> None:
        irrelevant_route = {
            "route_type": "noise",
            "is_relevant": False,
            "candidate_subjects": [],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.99,
            "reason": "The input was noise.",
        }
        stream_response.return_value = iter(
            [
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "Sorry?"
                        "<route>"
                        + json.dumps(
                            irrelevant_route
                        )
                        + "</route>"
                    ),
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="raw response",
                    done=True,
                ),
            ]
        )
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
            self_routing_enabled=True,
        )

        result = engine.generate_streaming_response(
            text="[background noise]",
            include_debug=True,
        )

        self.assertEqual(result.response, "Sorry?")
        self.assertFalse(
            result.debug.debug_payload[
                "self_routing_consistent"
            ]
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_cancelled_stream_does_not_require_footer(
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
                    text="Partial answer.<rou",
                ),
                LLMStreamEvent(
                    event_type="response_cancelled",
                    done=True,
                ),
                # A defensive regression case: nothing after
                # cancellation should trigger normal finalisation.
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

        result = engine.generate_streaming_response(
            text="Interrupted question",
            include_debug=True,
            on_stream_event=events.append,
        )

        self.assertEqual(
            result.response,
            "Partial answer.",
        )
        self.assertIsNone(
            result.debug.debug_payload[
                "self_routing_validation_error"
            ]
        )
        self.assertFalse(
            result.debug.debug_payload[
                "self_routing_valid"
            ]
        )
        self.assertNotIn(
            "self_routing",
            [event.event_type for event in events],
        )
        self.assertEqual(
            [
                event.event_type
                for event in events
                if event.event_type != "timing"
            ],
            [
                "response_started",
                "content_delta",
                "response_cancelled",
            ],
        )

        history = get_recent_conversation_history(
            result.conversation_id
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].role, "user")

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_streaming_ignored_turn_stores_no_assistant(
        self,
        stream_response,
    ) -> None:
        route = {
            "route_type": "noise",
            "is_relevant": False,
            "candidate_subjects": [],
            "should_update_subject": False,
            "proposed_action": None,
            "confidence": 0.99,
            "reason": "The input was noise.",
        }
        stream_response.return_value = iter(
            [
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "<route>"
                        + json.dumps(route)
                        + "</route>"
                    ),
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

        result = engine.generate_streaming_response(
            text="[background noise]",
            include_debug=True,
            on_stream_event=events.append,
        )

        self.assertEqual(result.response, "")
        self.assertTrue(
            result.debug.debug_payload[
                "self_routing_valid"
            ]
        )
        self.assertTrue(
            result.debug.debug_payload[
                "self_routing_consistent"
            ]
        )
        self.assertNotIn(
            "content_delta",
            [event.event_type for event in events],
        )

        history = get_recent_conversation_history(
            result.conversation_id
        )
        self.assertEqual(
            [turn.role for turn in history],
            ["user"],
        )

    @patch(
        "conversation_core.services."
        "query_service."
        "stream_tool_aware_llm_response"
    )
    def test_tool_events_are_not_deferred(
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
                        "Tour started."
                        "<route>"
                        + VALID_ROUTE_JSON
                        + "</route>"
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
                "tool_call",
                "tool_result",
                "content_delta",
                "self_routing",
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
