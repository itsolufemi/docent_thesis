from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from conversation_core.schemas.tool_schemas import (
    ToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)


ToolHandler = Callable[
    [ToolExecutionContext, dict[str, Any]],
    ToolExecutionResult,
]


class RegisteredTool:
    """
    Holds both the public tool definition and its
    private Python implementation.
    """

    def __init__(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
    ):
        self.definition = definition
        self.handler = handler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
    ) -> None:
        if definition.name in self._tools:
            raise ValueError(
                f"Tool '{definition.name}' is already registered."
            )

        self._tools[definition.name] = RegisteredTool(
            definition=definition,
            handler=handler,
        )

    def get_definitions(self) -> list[ToolDefinition]:
        return [
            registered_tool.definition
            for registered_tool in self._tools.values()
        ]

    def get_definition(
        self,
        tool_name: str,
    ) -> ToolDefinition | None:
        registered_tool = self._tools.get(
            tool_name
        )

        if registered_tool is None:
            return None

        return registered_tool.definition

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def execute(
        self,
        tool_call: ToolCall,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        registered_tool = self._tools.get(tool_call.name)

        if registered_tool is None:
            return ToolExecutionResult(
                tool_name=tool_call.name,
                success=False,
                message=f"Unknown tool: {tool_call.name}",
            )

        try:
            return registered_tool.handler(
                context,
                tool_call.arguments,
            )

        except ValidationError as error:
            return ToolExecutionResult(
                tool_name=tool_call.name,
                success=False,
                message="The tool arguments were invalid.",
                data={
                    "validation_errors": error.errors(),
                },
            )

        except Exception as error:
            return ToolExecutionResult(
                tool_name=tool_call.name,
                success=False,
                message=f"Tool execution failed: {error}",
            )
