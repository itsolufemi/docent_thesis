import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.conversation_store import (
    get_recent_conversation_history,
)
from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)
from conversation_core.schemas.query_schemas import (
    ResolvedContext,
)
from conversation_core.services.query_service import (
    QueryEngine,
)
from conversation_core.services.cancellation import (
    CancellationToken,
)


def resolve_context(
    subject_reference,
    user_input,
    utterance_route=None,
):
    return ResolvedContext(
        context_source="no_external_context",
        subject_reference=subject_reference,
    )


def build_prompt(
    user_input,
    dialogue_history,
    resolved_context,
    active_branch,
):
    return "streaming prompt"


class QueryStreamingServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.query_service."
        "stream_tool_aware_llm_response"
    )
    def test_streamed_response_is_assembled_and_stored_once(
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
            text="Question",
            on_stream_event=observed_events.append,
        )

        self.assertEqual(
            result.response,
            "A streamed answer.",
        )
        self.assertEqual(
            [
                event.event_type
                for event in observed_events
            ],
            [
                "response_started",
                "content_delta",
                "content_delta",
                "response_complete",
            ],
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

    def test_cancelled_response_stores_only_user_turn(
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
            ],
            ["response_cancelled"],
        )

        history = get_recent_conversation_history(
            conversation_id=result.conversation_id,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].role, "user")


if __name__ == "__main__":
    unittest.main(verbosity=2)
