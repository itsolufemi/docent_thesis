import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.turn_buffer_store import turn_buffer_store
from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.turn_buffer_schemas import TurnBufferEvent
from conversation_core.schemas.turn_detection_schemas import (
    TurnDetectionResult,
)
from conversation_core.services.turn_buffer_service import process_turn_event


def detection_result(
    *,
    complete: bool,
    probability: float,
) -> TurnDetectionResult:
    return TurnDetectionResult(
        decision=(
            "finalise_turn"
            if complete
            else "await_more_speech"
        ),
        should_call_trp=True,
        should_finalise_turn=complete,
        silence_duration_ms=500,
        trp_probability=probability,
        trp_prediction_seconds=0.25,
        reason="Test detection.",
    )


class TurnBufferServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.turn_buffer_service."
        "detect_turn_completion"
    )
    @patch(
        "conversation_core.services.turn_buffer_service."
        "get_recent_conversation_history"
    )
    def test_recent_conversation_history_is_passed_to_turn_detection(
        self,
        get_recent_history,
        detect_turn,
    ) -> None:
        conversation_id = "contextual-turn"
        turn_buffer_store.clear(conversation_id)
        get_recent_history.return_value = [
            DialogueTurn(
                role="assistant",
                content=(
                    "Would you like to hear about its history or "
                    "composition?"
                ),
            ),
        ]
        detect_turn.return_value = detection_result(
            complete=True,
            probability=0.95,
        )

        result = process_turn_event(
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="Its history.",
                is_speech_active=False,
                silence_duration_ms=500,
            )
        )

        self.assertEqual(result.decision, "finalise_turn")
        get_recent_history.assert_called_once_with(
            conversation_id=conversation_id,
            limit=4,
        )
        detect_turn.assert_called_once_with(
            partial_utterance="Its history.",
            is_speech_active=False,
            silence_duration_ms=500,
            previous_turns=[
                "assistant: Would you like to hear about its history or "
                "composition?",
            ],
        )

    @patch(
        "conversation_core.services.turn_buffer_service."
        "detect_turn_completion"
    )
    def test_voice_like_event_sequence(self, detect_turn) -> None:
        conversation_id = "test-conversation"
        turn_buffer_store.clear(conversation_id)
        detect_turn.side_effect = [
            detection_result(complete=False, probability=0.1),
            detection_result(complete=True, probability=0.95),
        ]

        events = [
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="tell me about",
                is_speech_active=True,
                silence_duration_ms=0,
            ),
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="tell me about",
                is_speech_active=False,
                silence_duration_ms=500,
            ),
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="tell me about",
                is_speech_active=False,
                silence_duration_ms=900,
            ),
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="tell me about The Arab Tent",
                is_speech_active=True,
                silence_duration_ms=0,
            ),
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="tell me about The Arab Tent",
                is_speech_active=False,
                silence_duration_ms=500,
            ),
        ]
        results = [
            process_turn_event(event)
            for event in events
        ]

        self.assertEqual(
            [result.decision for result in results],
            [
                "continue_listening",
                "await_more_speech",
                "await_more_speech",
                "continue_listening",
                "finalise_turn",
            ],
        )
        self.assertFalse(results[0].should_finalise_turn)
        self.assertEqual(
            results[1].state.last_evaluated_transcript,
            "tell me about",
        )
        self.assertEqual(results[1].state.last_trp_probability, 0.1)
        self.assertIn("already been evaluated", results[2].reason)
        self.assertTrue(results[4].should_finalise_turn)
        self.assertEqual(
            results[4].finalised_utterance,
            "tell me about The Arab Tent",
        )
        self.assertTrue(results[4].state.is_finalised)
        self.assertEqual(detect_turn.call_count, 2)

        cleared_buffer = turn_buffer_store.get_or_create(conversation_id)
        self.assertEqual(cleared_buffer.transcript, "")
        self.assertFalse(cleared_buffer.is_finalised)

    @patch(
        "conversation_core.services.turn_buffer_service."
        "detect_turn_completion"
    )
    def test_long_unchanged_pause_finalises_without_second_trp(
        self,
        detect_turn,
    ) -> None:
        conversation_id = "abandoned-turn"
        turn_buffer_store.clear(conversation_id)
        detect_turn.return_value = detection_result(
            complete=False,
            probability=0.1,
        )

        first_result = process_turn_event(
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="I think that the painting is",
                is_speech_active=False,
                silence_duration_ms=500,
            )
        )
        final_result = process_turn_event(
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance="I think that the painting is",
                is_speech_active=False,
                silence_duration_ms=2000,
            )
        )

        self.assertEqual(first_result.decision, "await_more_speech")
        self.assertEqual(final_result.decision, "finalise_turn")
        self.assertTrue(final_result.should_finalise_turn)
        self.assertEqual(
            final_result.finalised_utterance,
            "I think that the painting is",
        )
        self.assertIn("maximum silence", final_result.reason)
        detect_turn.assert_called_once()

    @patch(
        "conversation_core.services.turn_buffer_service."
        "detect_turn_completion"
    )
    def test_confirmed_audio_turn_bypasses_text_trp(
        self,
        detect_turn,
    ) -> None:
        conversation_id = "smart-turn-confirmed"
        turn_buffer_store.clear(conversation_id)

        result = process_turn_event(
            TurnBufferEvent(
                conversation_id=conversation_id,
                partial_utterance=(
                    "Tell me about The Arab Tent."
                ),
                is_speech_active=False,
                silence_duration_ms=500,
                turn_completion_confirmed=True,
            )
        )

        self.assertTrue(result.should_finalise_turn)
        self.assertEqual(
            result.finalised_utterance,
            "Tell me about The Arab Tent.",
        )
        self.assertIn(
            "confirmed before transcription",
            result.reason,
        )
        detect_turn.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
