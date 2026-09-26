from __future__ import annotations

import unittest

from unittest.mock import Mock, patch

from conversation_core.schemas.tool_schemas import (
    ToolDefinition,
    ToolExecutionResult,
)
from conversation_core.services.llm_service import (
    build_ollama_tool_definitions,
    stream_tool_aware_llm_response,
)
from conversation_core.tools.tool_registry import (
    ToolRegistry,
)


class ToolRegistryInjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.handler = Mock(
            return_value=ToolExecutionResult(
                tool_name="sandbox_lookup",
                success=True,
                message="Lookup complete.",
                data={"answer": "result"},
            )
        )
        self.registry.register(
            ToolDefinition(
                name="sandbox_lookup",
                description="Look up a sandbox value.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            self.handler,
        )

    def test_builds_definitions_from_supplied_registry(self) -> None:
        definitions = build_ollama_tool_definitions(
            self.registry
        )

        self.assertEqual(
            definitions[0]["function"]["name"],
            "sandbox_lookup",
        )

    @patch(
        "conversation_core.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_executes_against_supplied_registry(self, stream_request) -> None:
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "sandbox_lookup",
                                        "arguments": {},
                                    }
                                }
                            ],
                        },
                        "done": True,
                    }
                ]
            ),
            iter(
                [
                    {
                        "message": {
                            "content": "Finished.",
                        },
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Use the tool.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        self.handler.assert_called_once()
        tool_result = next(
            event
            for event in events
            if event.event_type == "tool_result"
        )
        self.assertEqual(
            tool_result.tool_name,
            "sandbox_lookup",
        )


if __name__ == "__main__":
    unittest.main()
