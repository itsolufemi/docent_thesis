import sys
import unittest
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.tools.core_tool_registry import (  # noqa: E402
    core_tool_registry,
)
from conversation_core.api.routes_conversation import (  # noqa: E402
    router,
)


class ConversationTreeToolRegistryTest(unittest.TestCase):
    def test_update_active_branch_is_not_registered(
        self,
    ) -> None:
        tool_names = {
            definition.name
            for definition
            in core_tool_registry.get_definitions()
        }

        self.assertNotIn(
            "update_active_branch",
            tool_names,
        )

    def test_activity_branch_tools_remain_registered(
        self,
    ) -> None:
        tool_names = {
            definition.name
            for definition
            in core_tool_registry.get_definitions()
        }

        self.assertIn(
            "create_conversation_branch",
            tool_names,
        )
        self.assertIn(
            "close_active_branch",
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
