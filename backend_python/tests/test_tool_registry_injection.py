from __future__ import annotations

import unittest

import json

from unittest.mock import Mock, patch

from conversation_core.schemas.source_schemas import QuerySource
from conversation_core.schemas.tool_schemas import (
    ToolDialogueStateUpdate,
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
                data={
                    "evidence": [
                        {
                            "text": "Evidence only once.",
                        }
                    ]
                },
                dialogue_state=ToolDialogueStateUpdate(
                    subjects=["The Swing"],
                    references=["painting:581"],
                ),
                sources=[
                    QuerySource(
                        source_type="retrieved_chunk",
                        reference="painting:581",
                        snippet="Evidence only once.",
                    )
                ],
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
        self.assertEqual(
            tool_result.tool_result["dialogue_state"]["subjects"],
            ["The Swing"],
        )
        self.assertEqual(
            tool_result.tool_result["sources"][0]["snippet"],
            "Evidence only once.",
        )

        second_round_messages = (
            stream_request.call_args_list[1].kwargs["messages"]
        )
        model_tool_message = next(
            message
            for message in second_round_messages
            if message["role"] == "tool"
        )
        model_payload = json.loads(
            model_tool_message["content"]
        )
        self.assertEqual(
            model_payload,
            {
                "success": True,
                "message": "Lookup complete.",
                "data": {
                    "evidence": [
                        {
                            "text": "Evidence only once.",
                        }
                    ]
                },
            },
        )
        self.assertNotIn("dialogue_state", model_payload)
        self.assertNotIn("sources", model_payload)
        self.assertNotIn("retrieval_used", model_payload)

    @patch(
        "conversation_core.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_completion_accumulates_text_before_silent_tool_round(
        self,
        stream_request,
    ) -> None:
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": "Primary answer.",
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
                        "message": {"content": ""},
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Answer, then inspect.",
                conversation_id="conversation-a",
                request_id="request-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        completion = next(
            event
            for event in events
            if event.event_type == "response_complete"
        )
        self.assertEqual(completion.text, "Primary answer.")
        context = self.handler.call_args.args[0]
        self.assertEqual(context.request_id, "request-a")
        self.assertEqual(
            context.visitor_facing_text,
            "Primary answer.",
        )

    @patch(
        "conversation_core.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_post_tool_continuation_is_separated_and_timed(
        self,
        stream_request,
    ) -> None:
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": "Primary answer.",
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
                        "message": {"content": "Continuation."},
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Answer, then inspect.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        completion = next(
            event
            for event in events
            if event.event_type == "response_complete"
        )
        self.assertEqual(
            completion.text,
            "Primary answer.\n\nContinuation.",
        )
        timing_names = {
            event.timing_name
            for event in events
            if event.event_type == "timing"
        }
        self.assertIn("last_content_to_tool_call_seconds", timing_names)
        self.assertIn("tool_execution_seconds", timing_names)
        self.assertIn(
            "tool_result_to_first_content_seconds",
            timing_names,
        )


if __name__ == "__main__":
    unittest.main()
