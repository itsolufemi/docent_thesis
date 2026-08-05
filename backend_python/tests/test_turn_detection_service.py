import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.schemas.trp_schemas import TRPPrediction
from conversation_core.services.turn_detection_service import (
    FORCED_FINALISATION_SILENCE_MS,
    detect_turn_completion,
)


def trp_prediction(
    probability: float,
    turn_complete: bool,
) -> TRPPrediction:
    return TRPPrediction(
        trp_probability=probability,
        turn_complete=turn_complete,
        reason="Test prediction.",
        prediction_seconds=0.25,
    )


class TurnDetectionServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.turn_detection_service."
        "predict_transition_relevance"
    )
    def test_active_speech_continues_without_trp(self, predict_trp) -> None:
        result = detect_turn_completion(
            partial_utterance="tell me about",
            is_speech_active=True,
            silence_duration_ms=0,
        )

        self.assertEqual(result.decision, "continue_listening")
        self.assertFalse(result.should_call_trp)
        self.assertFalse(result.should_finalise_turn)
        predict_trp.assert_not_called()

    @patch(
        "conversation_core.services.turn_detection_service."
        "predict_transition_relevance"
    )
    def test_short_pause_continues_without_trp(self, predict_trp) -> None:
        result = detect_turn_completion(
            partial_utterance="tell me about",
            is_speech_active=False,
            silence_duration_ms=150,
        )

        self.assertEqual(result.decision, "continue_listening")
        self.assertFalse(result.should_call_trp)
        self.assertFalse(result.should_finalise_turn)
        predict_trp.assert_not_called()

    @patch(
        "conversation_core.services.turn_detection_service."
        "predict_transition_relevance"
    )
    def test_incomplete_utterance_awaits_more_speech(self, predict_trp) -> None:
        predict_trp.return_value = trp_prediction(0.1, False)

        result = detect_turn_completion(
            partial_utterance="tell me about",
            is_speech_active=False,
            silence_duration_ms=500,
        )

        self.assertEqual(result.decision, "await_more_speech")
        self.assertTrue(result.should_call_trp)
        self.assertFalse(result.should_finalise_turn)
        self.assertEqual(result.trp_probability, 0.1)
        predict_trp.assert_called_once()

    @patch(
        "conversation_core.services.turn_detection_service."
        "predict_transition_relevance"
    )
    def test_complete_utterance_finalises(self, predict_trp) -> None:
        predict_trp.return_value = trp_prediction(0.95, True)

        result = detect_turn_completion(
            partial_utterance="tell me about The Arab Tent",
            is_speech_active=False,
            silence_duration_ms=500,
        )

        self.assertEqual(result.decision, "finalise_turn")
        self.assertTrue(result.should_call_trp)
        self.assertTrue(result.should_finalise_turn)
        self.assertEqual(result.trp_probability, 0.95)

    @patch(
        "conversation_core.services.turn_detection_service."
        "predict_transition_relevance"
    )
    def test_long_pause_forces_finalisation(self, predict_trp) -> None:
        predict_trp.return_value = trp_prediction(0.1, False)

        result = detect_turn_completion(
            partial_utterance="I think that the painting is",
            is_speech_active=False,
            silence_duration_ms=(
                FORCED_FINALISATION_SILENCE_MS
            ),
        )

        self.assertEqual(result.decision, "finalise_turn")
        self.assertTrue(result.should_call_trp)
        self.assertTrue(result.should_finalise_turn)

    @patch(
        "conversation_core.services.turn_detection_service."
        "predict_transition_relevance"
    )
    def test_voice_like_event_sequence(self, predict_trp) -> None:
        predict_trp.return_value = trp_prediction(0.95, True)

        events = [
            ("tell me about", True, 0),
            ("tell me about", False, 200),
            ("tell me about The Arab Tent", True, 0),
            ("tell me about The Arab Tent", False, 500),
        ]
        decisions = [
            detect_turn_completion(
                partial_utterance=utterance,
                is_speech_active=is_speech_active,
                silence_duration_ms=silence_duration_ms,
            ).decision
            for utterance, is_speech_active, silence_duration_ms in events
        ]

        self.assertEqual(
            decisions,
            [
                "continue_listening",
                "continue_listening",
                "continue_listening",
                "finalise_turn",
            ],
        )
        predict_trp.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
