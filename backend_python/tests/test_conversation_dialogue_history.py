import sys
import unittest
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    add_dialogue_turn,
    conversations,
    create_conversation,
)
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    DialogueTurn,
)
from conversation_core.services.prompt_service import (  # noqa: E402
    format_dialogue_history_for_prompt,
)


class ConversationDialogueHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()

    def tearDown(self) -> None:
        conversations.clear()

    def test_add_dialogue_turn_stores_subject_snapshot(self) -> None:
        state = create_conversation()

        add_dialogue_turn(
            state.conversation_id,
            "user",
            "Tell me about The Arab Tent.",
            previous_subject="The Swing",
            current_subject="The Arab Tent",
            current_subject_reference="painting:581",
        )

        turn = state.dialogue_history[0]

        self.assertEqual(turn.previous_subject, "The Swing")
        self.assertEqual(turn.current_subject, "The Arab Tent")
        self.assertEqual(
            turn.current_subject_reference,
            "painting:581",
        )

    def test_prompt_history_includes_available_subject_snapshot(self) -> None:
        history = [
            DialogueTurn(
                role="assistant",
                content="The Arab Tent is...",
                previous_subject="The Swing",
                current_subject="The Arab Tent",
                current_subject_reference="painting:581",
            ),
        ]

        self.assertEqual(
            format_dialogue_history_for_prompt(history),
            (
                "Assistant: The Arab Tent is...\n"
                "Subject state: previous='The Swing'; "
                "current='The Arab Tent'; "
                "current_reference='painting:581'"
            ),
        )

    def test_legacy_turn_format_remains_unchanged(self) -> None:
        history = [
            DialogueTurn(
                role="user",
                content="Hello.",
            ),
        ]

        self.assertEqual(
            format_dialogue_history_for_prompt(history),
            "User: Hello.",
        )


if __name__ == "__main__":
    unittest.main()
