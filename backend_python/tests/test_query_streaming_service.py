import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.conversation_store import conversations, get_recent_conversation_history  # noqa: E402
from conversation_core.schemas.llm_stream_schemas import LLMStreamEvent  # noqa: E402
from conversation_core.schemas.query_schemas import ResolvedContext  # noqa: E402
from conversation_core.schemas.source_schemas import QuerySource  # noqa: E402
from conversation_core.services.cancellation import CancellationToken  # noqa: E402
from conversation_core.services.query_service import QueryEngine  # noqa: E402


def resolve_context(dialogue_history, user_input, utterance_route=None):
    return ResolvedContext(
        context_source="subject_vector_retrieval",
        sources=[QuerySource(source_type="retrieved_chunk", reference="painting:581")],
        prompt_payload={
            "subjects": ["The Arab Tent"],
            "context_resolution": {
                "is_relevant": True,
                "route_type": "response_request",
                "requires_retrieval": True,
                "subjects": ["The Arab Tent"],
            },
        },
    )


def build_prompt(user_input, dialogue_history, resolved_context):
    return f"Streaming prompt for: {user_input}"


class QueryStreamingServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()

    @patch("conversation_core.services.query_service.stream_llm_response")
    def test_streamed_response_completes_one_exchange(self, stream_response) -> None:
        stream_response.return_value = iter([
            LLMStreamEvent(event_type="response_started"),
            LLMStreamEvent(event_type="content_delta", text="A streamed "),
            LLMStreamEvent(event_type="content_delta", text="answer."),
            LLMStreamEvent(event_type="response_complete", text="A streamed answer.", done=True),
        ])
        observed_events = []
        engine = QueryEngine(subject_resolver=resolve_context, prompt_builder=build_prompt)

        result = engine.generate_streaming_response(
            text="Tell me about The Arab Tent.",
            on_stream_event=observed_events.append,
            include_debug=True,
        )

        self.assertEqual(result.response, "A streamed answer.")
        self.assertEqual(
            [event.event_type for event in observed_events if event.event_type != "timing"],
            ["self_routing", "response_started", "content_delta", "content_delta", "response_complete"],
        )
        history = get_recent_conversation_history(result.conversation_id)
        self.assertEqual(len(history), 1)
        exchange = history[0]
        self.assertEqual(exchange.previous_subject, [])
        self.assertEqual(exchange.subject, ["The Arab Tent"])
        self.assertEqual(exchange.reference, ["painting:581"])
        self.assertEqual(exchange.user, "Tell me about The Arab Tent.")
        self.assertEqual(exchange.assistant, "A streamed answer.")

    @patch("conversation_core.services.query_service.stream_llm_response")
    def test_context_resolution_event_is_emitted_before_response_stream(self, stream_response) -> None:
        stream_response.return_value = iter([
            LLMStreamEvent(event_type="response_started"),
            LLMStreamEvent(event_type="content_delta", text="Answer."),
            LLMStreamEvent(event_type="response_complete", text="Answer.", done=True),
        ])
        observed_events = []
        engine = QueryEngine(subject_resolver=resolve_context, prompt_builder=build_prompt)
        engine.generate_streaming_response(text="Question", on_stream_event=observed_events.append)

        non_timing_events = [event for event in observed_events if event.event_type != "timing"]
        self.assertEqual(non_timing_events[0].event_type, "self_routing")
        self.assertEqual(non_timing_events[0].route_assessment["subjects"], ["The Arab Tent"])
        self.assertEqual(non_timing_events[1].event_type, "response_started")

    def test_cancelled_response_keeps_pending_exchange(self) -> None:
        token = CancellationToken()
        token.cancel()
        observed_events = []
        engine = QueryEngine(subject_resolver=resolve_context, prompt_builder=build_prompt)

        result = engine.generate_streaming_response(
            text="Interrupted question",
            on_stream_event=observed_events.append,
            cancellation_token=token,
        )

        self.assertEqual(result.response, "")
        history = get_recent_conversation_history(result.conversation_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].subject, ["The Arab Tent"])
        self.assertEqual(history[0].reference, ["painting:581"])
        self.assertEqual(history[0].user, "Interrupted question")
        self.assertIsNone(history[0].assistant)


if __name__ == "__main__":
    unittest.main(verbosity=2)
