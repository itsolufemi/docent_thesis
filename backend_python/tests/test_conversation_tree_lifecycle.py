import sys
import unittest
from pathlib import Path

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.conversation_store import (
    close_bounded_branch,
    conversations,
    create_conversation,
    create_conversation_branch,
)


class ConversationTreeLifecycleTest(unittest.TestCase):
    def tearDown(self) -> None:
        conversations.clear()

    def assert_single_active_branch(self, state) -> None:
        tree = state.conversation_tree
        active_branches = [
            branch
            for branch in tree.branches.values()
            if branch.status == "active"
        ]

        self.assertEqual(len(active_branches), 1)
        self.assertEqual(
            active_branches[0].branch_id,
            tree.active_branch_id,
        )

    def test_closing_bounded_branch_creates_new_open_branch(self) -> None:
        state = create_conversation()
        tree = state.conversation_tree
        first_branch_id = tree.active_branch_id

        serialised_tree = tree.model_dump()
        self.assertNotIn("root_branch_id", serialised_tree)
        self.assertNotIn(
            "parent_branch_id",
            serialised_tree["branches"][first_branch_id],
        )

        state = create_conversation_branch(
            conversation_id=state.conversation_id,
            branch_type="bounded",
        )

        self.assertIsNotNone(state)
        tree = state.conversation_tree
        second_branch_id = tree.active_branch_id

        state = close_bounded_branch(state.conversation_id)

        self.assertIsNotNone(state)
        tree = state.conversation_tree
        third_branch_id = tree.active_branch_id

        self.assertEqual(tree.branches[first_branch_id].name, "branch-1")
        self.assertEqual(tree.branches[first_branch_id].status, "closed")
        self.assertEqual(tree.branches[second_branch_id].name, "branch-2")
        self.assertEqual(tree.branches[second_branch_id].status, "closed")
        self.assertEqual(tree.branches[third_branch_id].name, "branch-3")
        self.assertEqual(tree.branches[third_branch_id].status, "active")
        self.assertEqual(tree.branches[third_branch_id].branch_type, "open")
        self.assert_single_active_branch(state)

    def test_creating_each_branch_preserves_single_active_invariant(self) -> None:
        state = create_conversation()

        for branch_type in ("bounded", "open", "bounded"):
            state = create_conversation_branch(
                conversation_id=state.conversation_id,
                branch_type=branch_type,
            )
            self.assertIsNotNone(state)
            self.assert_single_active_branch(state)

    def test_open_branch_cannot_be_closed_as_bounded(self) -> None:
        state = create_conversation()

        with self.assertRaisesRegex(
            ValueError,
            "The active branch is not bounded.",
        ):
            close_bounded_branch(state.conversation_id)

        self.assert_single_active_branch(state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
