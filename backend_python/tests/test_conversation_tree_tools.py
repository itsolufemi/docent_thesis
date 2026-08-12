import sys
import unittest
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.tools.core_tool_registry import (  # noqa: E402
    core_tool_registry,
)
from conversation_core.memory.conversation_store import (  # noqa: E402
    create_conversation,
)
from conversation_core.api.routes_conversation import (  # noqa: E402
    router,
)


class ConversationTreeRemovalTest(unittest.TestCase):
    def test_conversation_state_contains_no_tree(
        self,
    ) -> None:
        state = create_conversation()

        self.assertNotIn(
            "conversation_tree",
            state.model_dump(mode="json"),
        )

    def test_conversation_tree_tools_are_disconnected(
        self,
    ) -> None:
        tool_names = {
            definition.name
            for definition
            in core_tool_registry.get_definitions()
        }

        self.assertNotIn(
            "create_conversation_branch",
            tool_names,
        )
        self.assertNotIn(
            "close_active_branch",
            tool_names,
        )
        self.assertNotIn(
            "update_active_branch",
            tool_names,
        )


class ConversationRouteTest(unittest.TestCase):
    def test_active_branch_subject_route_is_removed(
        self,
    ) -> None:
        route_paths = {
            route.path
            for route in router.routes
        }

        self.assertNotIn(
            (
                "/api/conversations/current/"
                "active-branch/subject"
            ),
            route_paths,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
