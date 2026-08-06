import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.conversation_store import (  # noqa: E402
    conversations,
    get_recent_conversation_history,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    ResolvedContext,
)
from conversation_core.services.cancellation import (  # noqa: E402
    CancellationToken,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)


def resolve_context(
    dialogue_history,
    user_input,
    utterance_route=None,
):
    return ResolvedContext(
        context_source="subject_vector_retrieval",
        prompt_payload={
            "subjects": ["The Arab Tent"],
            "context_resolution": {
                "is_relevant": True,
                "route_type": "response_request",
                "requires_retrieval": True,
                "subjects": ["The Arab Tent"],
            },
        },
        debug_payload={
            "context_resolution": {
                "is_relevant": True,
                "route_type": "response_request",
                "requires_retrieval": True,
                "subjects": ["The Arab Tent"],
            }
        },
    )


def build_prompt(
    user_input,
    dialogue_history,
    resolved_context,
):
    return f"Streaming prompt for: {user_input}"


class QueryStreamingServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()

    @patch(
        "conversation_core.services.query_service."
        "stream_llm_response"
    )
    def test_streamed_response_is_assembled_and_subjects_are_stored(
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
                    text="A streamed ",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="answer.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="A streamed answer.",
                    done=True,
                ),
            ]
        )
        observed_events = []
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
        )

        result = engine.generate_streaming_response(
            text="Tell me about The Arab Tent.",
            on_stream_event=observed_events.append,
            include_debug=True,
        )

        self.assertEqual(
            result.response,
            "A streamed answer.",
        )
        self.assertEqual(
            [
                event.event_type
                for event in observed_events
                if event.event_type != "timing"
            ],
            [
                "response_started",
                "content_delta",
                "content_delta",
                "response_complete",
            ],
        )

        stream_response.assert_called_once()
        self.assertEqual(
            stream_response.call_args.kwargs["prompt"],
            "Streaming prompt for: Tell me about The Arab Tent.",
        )

        history = get_recent_conversation_history(
            conversation_id=result.conversation_id,
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(
            [turn.role for turn in history],
            ["user", "assistant"],
        )
        self.assertEqual(
            history[1].content,
            "A streamed answer.",
        )
        self.assertEqual(
            history[0].subjects,
            ["The Arab Tent"],
        )
        self.assertEqual(
            history[1].subjects,
            ["The Arab Tent"],
        )

        self.assertIsNotNone(result.debug)
        self.assertEqual(
            result.debug.debug_payload["subjects"],
            ["The Arab Tent"],
        )

    @patch(
        "conversation_core.services.query_service."
        "stream_llm_response"
    )
    def test_context_resolution_event_is_emitted_before_response_stream(
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
                    text="Answer.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Answer.",
                    done=True,
                ),
            ]
        )
        observed_events = []
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
        )

        engine.generate_streaming_response(
            text="Question",
            on_stream_event=observed_events.append,
        )

        event_types = [
            event.event_type
            for event in observed_events
            if event.event_type != "timing"
        ]
        self.assertEqual(event_types[0], "self_routing")
        self.assertEqual(
            observed_events[0].route_assessment,
            {
                "is_relevant": True,
                "route_type": "response_request",
                "requires_retrieval": True,
                "subjects": ["The Arab Tent"],
            },
        )

    def test_cancelled_response_stores_only_user_turn_with_subjects(
        self,
    ) -> None:
        token = CancellationToken()
        token.cancel()
        observed_events = []
        engine = QueryEngine(
            subject_resolver=resolve_context,
            prompt_builder=build_prompt,
        )

        result = engine.generate_streaming_response(
            text="Interrupted question",
            on_stream_event=observed_events.append,
            cancellation_token=token,
        )

        self.assertEqual(result.response, "")
        self.assertEqual(
            [
                event.event_type
                for event in observed_events
                if event.event_type != "timing"
            ],
            [
                "self_routing",
                "response_cancelled",
            ],
        )

        history = get_recent_conversation_history(
            conversation_id=result.conversation_id,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(
            history[0].subjects,
            ["The Arab Tent"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
