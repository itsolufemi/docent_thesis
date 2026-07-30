from conversation_core.tools.conversation_tree_tools import (
    register_conversation_tree_tools,
)

from conversation_core.tools.tool_registry import ToolRegistry
from conversation_core.tools.utterance_classifier_tool import (
    register_utterance_classifier_tool,
)


core_tool_registry = ToolRegistry()

register_conversation_tree_tools(
    core_tool_registry
)

register_utterance_classifier_tool(
    core_tool_registry
)
