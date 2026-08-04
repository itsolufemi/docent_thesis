import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.memory.conversation_store import (
    create_conversation,
    get_conversation,
)

from conversation_core.services.llm_service import (
    generate_tool_aware_llm_response,
)
from conversation_core.tools.conversation_tree_tools import (
    register_conversation_tree_tools,
)
from conversation_core.tools.tool_registry import ToolRegistry


PROMPT = """
You are a conversational AI with access to operational tools.

The user has requested a gallery tour containing three paintings.

Use the appropriate tool to create a bounded conversation branch.

The branch must have:
- name: gallery tour
- current subject: The Swing
- remaining subjects:
  - The Laughing Cavalier
  - The Arab Tent

After the tool succeeds, briefly tell the user that the tour has begun.
""".strip()


def main() -> None:
    state = create_conversation()
    isolated_tree_registry = ToolRegistry()
    register_conversation_tree_tools(
        isolated_tree_registry
    )

    with patch(
        "conversation_core.services.llm_service.core_tool_registry",
        isolated_tree_registry,
    ):
        response = generate_tool_aware_llm_response(
            prompt=PROMPT,
            conversation_id=state.conversation_id,
        )

    print("LLM RESPONSE")
    print(response)

    updated_state = get_conversation(
        state.conversation_id
    )

    assert updated_state is not None

    print("\nUPDATED CONVERSATION")
    print(updated_state.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
