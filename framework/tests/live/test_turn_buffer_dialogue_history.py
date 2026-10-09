import sys
import unittest
from pathlib import Path
from unittest.mock import patch


FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FRAMEWORK_ROOT.parent

for import_root in (REPOSITORY_ROOT, FRAMEWORK_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from core_engine.memory.turn_buffer_store import turn_buffer_store  # noqa: E402
from core_engine.schemas.conversation_schemas import DialogueTurn  # noqa: E402
from core_engine.schemas.turn_buffer_schemas import TurnBufferEvent  # noqa: E402
from core_engine.schemas.turn_detection_schemas import TurnDetectionResult  # noqa: E402
from core_engine.services.turn_buffer_service import process_turn_event  # noqa: E402


class TurnBufferDialogueHistoryTests(unittest.TestCase):
    def test_exchange_shaped_history_is_passed_to_semantic_detection(self):
        conversation_id = "turn-history-regression"
        turn_buffer_store.clear(conversation_id)
        history = [
            DialogueTurn(assistant="Welcome to Docent."),
            DialogueTurn(
                user="Tell me about The Swing.",
                assistant="It was painted by Fragonard.",
            ),
            DialogueTurn(user="What about its history?"),
            DialogueTurn(),
        ]
        detection = TurnDetectionResult(
            decision="finalise_turn",
            should_call_trp=True,
            should_finalise_turn=True,
            silence_duration_ms=500,
            reason="Test completion.",
        )

        try:
            with (
                patch(
                    "core_engine.services.turn_buffer_service."
                    "get_recent_conversation_history",
                    return_value=history,
                ) as get_history,
                patch(
                    "core_engine.services.turn_buffer_service."
                    "detect_turn_completion",
                    return_value=detection,
                ) as detect,
            ):
                result = process_turn_event(
                    TurnBufferEvent(
                        conversation_id=conversation_id,
                        partial_utterance="Tell me more.",
                        is_speech_active=False,
                        silence_duration_ms=500,
                    )
                )

            self.assertTrue(result.should_finalise_turn)
            get_history.assert_called_once_with(
                conversation_id=conversation_id, limit=4
            )
            detect.assert_called_once_with(
                partial_utterance="Tell me more.",
                is_speech_active=False,
                silence_duration_ms=500,
                previous_turns=[
                    "assistant: Welcome to Docent.",
                    "user: Tell me about The Swing.",
                    "assistant: It was painted by Fragonard.",
                    "user: What about its history?",
                ],
            )
        finally:
            turn_buffer_store.clear(conversation_id)

    def test_confirmed_audio_turn_skips_semantic_detection(self):
        conversation_id = "confirmed-turn-regression"
        turn_buffer_store.clear(conversation_id)
        try:
            with patch(
                "core_engine.services.turn_buffer_service."
                "detect_turn_completion"
            ) as detect:
                result = process_turn_event(
                    TurnBufferEvent(
                        conversation_id=conversation_id,
                        partial_utterance="The Swing.",
                        is_speech_active=False,
                        silence_duration_ms=500,
                        turn_completion_confirmed=True,
                    )
                )
            self.assertTrue(result.should_finalise_turn)
            detect.assert_not_called()
        finally:
            turn_buffer_store.clear(conversation_id)


if __name__ == "__main__":
    unittest.main()
