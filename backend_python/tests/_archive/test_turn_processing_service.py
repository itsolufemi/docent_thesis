import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.schemas.query_schemas import QueryResult
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferEvent,
    TurnBufferResult,
    TurnBufferState,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.services.turn_processing_service import (
    process_conversation_turn,
)


class TurnProcessingServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.turn_processing_service."
        "process_turn_event"
    )
    def test_active_speech_does_not_run_query(
        self,
        process_turn,
    ) -> None:
        process_turn.return_value = TurnBufferResult(
            state=TurnBufferState(
                conversation_id="conversation-1",
                transcript="tell me about",
                is_speech_active=True,
            ),
            decision="continue_listening",
            should_finalise_turn=False,
            reason="Speech is active.",
        )
        query_engine = Mock()
        utterance_classifier = Mock()

        result = process_conversation_turn(
            event=TurnBufferEvent(
                conversation_id="conversation-1",
                partial_utterance="tell me about",
                is_speech_active=True,
                silence_duration_ms=0,
            ),
            query_engine=query_engine,
            utterance_classifier=utterance_classifier,
        )

        self.assertIsNone(result.query)
        self.assertIsNone(result.utterance_route)
        utterance_classifier.assert_not_called()
        query_engine.generate_response.assert_not_called()

    @patch(
        "conversation_core.services.turn_processing_service."
        "process_turn_event"
    )
    def test_incomplete_trp_does_not_run_query(
        self,
        process_turn,
    ) -> None:
        process_turn.return_value = TurnBufferResult(
            state=TurnBufferState(
                conversation_id="conversation-1",
                transcript="tell me about",
                silence_duration_ms=500,
            ),
            decision="await_more_speech",
            should_finalise_turn=False,
            reason="The utterance appears incomplete.",
        )
        query_engine = Mock()
        utterance_classifier = Mock()

        result = process_conversation_turn(
            event=TurnBufferEvent(
                conversation_id="conversation-1",
                partial_utterance="tell me about",
                is_speech_active=False,
                silence_duration_ms=500,
            ),
            query_engine=query_engine,
            utterance_classifier=utterance_classifier,
        )

        self.assertIsNone(result.query)
        self.assertIsNone(result.utterance_route)
        utterance_classifier.assert_not_called()
        query_engine.generate_response.assert_not_called()

    @patch(
        "conversation_core.services.turn_processing_service."
        "process_turn_event"
    )
    def test_finalised_turn_runs_query_once(
        self,
        process_turn,
    ) -> None:
        process_turn.return_value = TurnBufferResult(
            state=TurnBufferState(
                conversation_id="conversation-1",
                transcript="Tell me about The Arab Tent.",
                is_finalised=True,
            ),
            decision="finalise_turn",
            should_finalise_turn=True,
            finalised_utterance="Tell me about The Arab Tent.",
            reason="Turn complete.",
        )
        query_engine = Mock()
        query_engine.generate_response.return_value = QueryResult(
            request="Tell me about The Arab Tent.",
            response="The Arab Tent is...",
            conversation_id="conversation-1",
        )
        utterance_route = UtteranceRoute(
            route_type="response_request",
            floor_intent="take_floor",
            requires_retrieval=True,
            is_relevant=True,
            should_ignore=False,
            confidence=0.95,
            reason="The user asks a question.",
        )
        utterance_classifier = Mock(
            return_value=utterance_route,
        )

        result = process_conversation_turn(
            event=TurnBufferEvent(
                conversation_id="conversation-1",
                partial_utterance="Tell me about The Arab Tent.",
                is_speech_active=False,
                silence_duration_ms=500,
                assistant_was_speaking=True,
            ),
            query_engine=query_engine,
            utterance_classifier=utterance_classifier,
            include_debug=True,
        )

        utterance_classifier.assert_called_once_with(
            "Tell me about The Arab Tent.",
            True,
        )
        query_engine.generate_response.assert_called_once_with(
            text="Tell me about The Arab Tent.",
            conversation_id="conversation-1",
            subject_reference=None,
            utterance_route=utterance_route,
            include_debug=True,
        )
        self.assertIsNotNone(result.query)
        self.assertIs(
            result.utterance_route,
            utterance_route,
        )
        self.assertEqual(result.query.response, "The Arab Tent is...")


if __name__ == "__main__":
    unittest.main(verbosity=2)
