from conversation_core.tools.conversation_tree_tools import (
    register_conversation_tree_tools,
)

from conversation_core.tools.tool_registry import ToolRegistry


core_tool_registry = ToolRegistry()

register_conversation_tree_tools(
    core_tool_registry
)