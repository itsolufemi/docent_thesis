import sys
import unittest
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    close_active_branch,
    create_conversation,
    create_conversation_branch,
    get_active_branch,
)
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    ConversationSubject,
)


class ConversationTreeTest(unittest.TestCase):
    def test_bounded_activity_keeps_planned_subjects_until_closed(
        self,
    ) -> None:
        state = create_conversation()
        conversation_id = state.conversation_id

        tour_state = create_conversation_branch(
            conversation_id=conversation_id,
            name="gallery tour",
            branch_type="bounded",
            current_subjects=[
                ConversationSubject(
                    label="The Swing"
                ),
            ],
            remaining_subjects=[
                ConversationSubject(
                    label="The Laughing Cavalier"
                ),
                ConversationSubject(
                    label="The Arab Tent"
                ),
            ],
        )

        self.assertIsNotNone(tour_state)
        tour_branch = get_active_branch(
            conversation_id
        )
        self.assertIsNotNone(tour_branch)
        self.assertEqual(
            [
                subject.label
                for subject in tour_branch.current_subjects
            ],
            ["The Swing"],
        )
        self.assertEqual(
            [
                subject.label
                for subject in tour_branch.remaining_subjects
            ],
            [
                "The Laughing Cavalier",
                "The Arab Tent",
            ],
        )

        closed_state = close_active_branch(
            conversation_id
        )

        self.assertIsNotNone(closed_state)
        self.assertEqual(tour_branch.status, "closed")
        new_active_branch = get_active_branch(
            conversation_id
        )
        self.assertIsNotNone(new_active_branch)
        self.assertEqual(
            new_active_branch.branch_type,
            "open",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
