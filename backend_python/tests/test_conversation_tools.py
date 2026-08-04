import sys
from pathlib import Path

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.conversation_store import create_conversation
from conversation_core.schemas.tool_schemas import ToolCall, ToolExecutionContext
from conversation_core.tools.conversation_tree_tools import (
    register_conversation_tree_tools,
)
from conversation_core.tools.tool_registry import ToolRegistry


def main() -> None:
    tree_tool_registry = ToolRegistry()
    register_conversation_tree_tools(
        tree_tool_registry
    )

    state = create_conversation()
    context = ToolExecutionContext(
        conversation_id=state.conversation_id
    )

    create_result = tree_tool_registry.execute(
        tool_call=ToolCall(
            name="create_conversation_branch",
            arguments={
                "name": "gallery tour",
                "branch_type": "bounded",
                "current_subjects": [
                    {
                        "label": "The Swing",
                        "reference": "painting:1",
                    }
                ],
                "remaining_subjects": [
                    {
                        "label": "The Laughing Cavalier",
                        "reference": "painting:2",
                    },
                    {
                        "label": "The Arab Tent",
                        "reference": "painting:581",
                    },
                ],
            },
        ),
        context=context,
    )

    print("CREATE RESULT")
    print(create_result.model_dump_json(indent=2))

    close_result = tree_tool_registry.execute(
        tool_call=ToolCall(
            name="close_active_branch",
            arguments={
                "reason": "The user asked to stop the tour.",
            },
        ),
        context=context,
    )

    print("\nCLOSE RESULT")
    print(close_result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
