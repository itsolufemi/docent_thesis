from __future__ import annotations

import unittest

import json

from unittest.mock import Mock, patch

from core_engine.schemas.source_schemas import QuerySource
from core_engine.schemas.tool_schemas import (
    ToolDialogueStateUpdate,
    ToolDefinition,
    ToolExecutionResult,
)
from core_engine.services.llm_service import (
    build_ollama_tool_definitions,
    stream_tool_aware_llm_response,
)
from core_engine.tools.tool_registry import (
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

    @staticmethod
    def _discovery_registry(handler) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                name="discover_docent_knowledge",
                description="Discover one optional continuation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "scope": {"type": "string"},
                        "purpose": {"type": "string"},
                    },
                    "required": ["query", "scope"],
                },
                allowed_phases={
                    "primary",
                    "post_answer",
                },
            ),
            handler,
        )
        return registry

    @patch(
        "core_engine.services.llm_service."
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
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_complete_unbuffered_sentence_unlocks_later_tool(
        self,
        stream_request,
    ) -> None:
        captured_contexts = []

        def capture_context(context, _arguments):
            captured_contexts.append(context.model_copy(deep=True))
            return ToolExecutionResult(
                tool_name="sandbox_lookup",
                success=True,
                message="Lookup complete.",
            )

        self.handler.side_effect = capture_context
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": "A complete visitor answer.",
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
                        "message": {"content": "Finished."},
                        "done": True,
                    }
                ]
            ),
        ]

        list(
            stream_tool_aware_llm_response(
                prompt="Answer, then use the tool.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        self.assertTrue(captured_contexts[0].visitor_sentence_emitted)
        self.assertEqual(captured_contexts[0].executed_tool_names, [])

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_buffered_sentence_does_not_unlock_tool(
        self,
        stream_request,
    ) -> None:
        captured_contexts = []

        def capture_context(context, _arguments):
            captured_contexts.append(context.model_copy(deep=True))
            return ToolExecutionResult(
                tool_name="sandbox_lookup",
                success=True,
                message="Lookup complete.",
            )

        self.handler.side_effect = capture_context
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": "A buffered internal sentence.",
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
                        "message": {"content": "Finished."},
                        "done": True,
                    }
                ]
            ),
        ]

        list(
            stream_tool_aware_llm_response(
                prompt="Use the tool.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=True,
                tool_registry=self.registry,
            )
        )

        self.assertFalse(captured_contexts[0].visitor_sentence_emitted)

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_executed_tool_names_reach_later_tool_calls(
        self,
        stream_request,
    ) -> None:
        captured_contexts = []

        def capture_context(context, _arguments):
            captured_contexts.append(context.model_copy(deep=True))
            return ToolExecutionResult(
                tool_name="sandbox_lookup",
                success=True,
                message="Lookup complete.",
            )

        self.handler.side_effect = capture_context
        def tool_round(arguments):
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "sandbox_lookup",
                                "arguments": arguments,
                            }
                        }
                    ],
                },
                "done": True,
            }
        stream_request.side_effect = [
            iter([tool_round({"subject": "The Swing"})]),
            iter([tool_round({"subject": "Boucher"})]),
            iter(
                [
                    {
                        "message": {"content": "Finished."},
                        "done": True,
                    }
                ]
            ),
        ]

        list(
            stream_tool_aware_llm_response(
                prompt="Use the tool twice.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        self.assertEqual(captured_contexts[0].executed_tool_names, [])
        self.assertEqual(
            captured_contexts[1].executed_tool_names,
            ["sandbox_lookup"],
        )
        self.assertEqual(self.handler.call_count, 2)

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_exact_duplicate_tool_call_is_suppressed_and_recovered(
        self,
        stream_request,
    ) -> None:
        duplicate_round = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "sandbox_lookup",
                            "arguments": {"subject": "p487"},
                        }
                    }
                ],
            },
            "done": True,
        }
        stream_request.side_effect = [
            iter([duplicate_round]),
            iter([duplicate_round]),
            iter(
                [
                    {
                        "message": {"content": "Finished from evidence."},
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Use the same evidence once.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        self.handler.assert_called_once()
        suppressed = next(
            event
            for event in events
            if event.event_type == "tool_call_suppressed"
        )
        self.assertEqual(
            suppressed.tool_telemetry["response_phase"],
            "primary",
        )
        self.assertTrue(
            suppressed.tool_telemetry["duplicate"]
        )
        self.assertEqual(
            suppressed.tool_telemetry["reason"],
            "duplicate_call_same_phase",
        )
        self.assertIn(
            'sandbox_lookup:{"subject":"p487"}',
            suppressed.tool_telemetry["call_signature"],
        )
        self.assertIn(
            "already been executed",
            stream_request.call_args_list[2].kwargs["messages"][-1]["content"],
        )
        emitted = "".join(
            event.text
            for event in events
            if event.event_type == "content_delta"
        )
        self.assertEqual(emitted, "Finished from evidence.")

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_post_answer_phase_exposes_discovery_but_not_primary_tool(
        self,
        stream_request,
    ) -> None:
        discovery_handler = Mock(
            return_value=ToolExecutionResult(
                tool_name="discover_docent_knowledge",
                success=True,
                message="Discovery complete.",
            )
        )
        self.registry.register(
            ToolDefinition(
                name="discover_docent_knowledge",
                description="Discover an optional continuation.",
                allowed_phases={"primary", "post_answer"},
                parameters={
                    "type": "object",
                    "properties": {},
                },
            ),
            discovery_handler,
        )
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
                                        "arguments": {"subject": "The Swing"},
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
                        "message": {"content": "Primary answer."},
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
                prompt="Tell me about The Swing.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=self.registry,
            )
        )

        self.handler.assert_called_once()
        discovery_handler.assert_not_called()
        primary_names = {
            tool["function"]["name"]
            for tool in stream_request.call_args_list[0].kwargs["tools"]
        }
        self.assertEqual(
            primary_names,
            {"sandbox_lookup", "discover_docent_knowledge"},
        )
        post_answer_names = {
            tool["function"]["name"]
            for tool in stream_request.call_args_list[2].kwargs["tools"]
        }
        self.assertEqual(
            post_answer_names,
            {"discover_docent_knowledge"},
        )
        tool_call = next(
            event
            for event in events
            if event.event_type == "tool_call"
        )
        self.assertEqual(
            tool_call.tool_telemetry["response_phase"],
            "primary",
        )
        self.assertFalse(tool_call.tool_telemetry["duplicate"])

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_no_discovery_probe_finishes_without_streaming_probe_text(
        self,
        stream_request,
    ) -> None:
        handler = Mock()
        registry = self._discovery_registry(handler)
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {"content": "Primary answer."},
                        "done": True,
                    }
                ]
            ),
            iter(
                [
                    {
                        "message": {"content": "No discovery needed."},
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Give a short factual answer.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=registry,
            )
        )

        emitted = "".join(
            event.text
            for event in events
            if event.event_type == "content_delta"
        )
        self.assertEqual(emitted, "Primary answer.")
        self.assertEqual(events[-1].event_type, "response_complete")
        self.assertEqual(events[-1].text, "")
        handler.assert_not_called()
        probe_call = stream_request.call_args_list[1]
        self.assertEqual(
            [tool["function"]["name"] for tool in probe_call.kwargs["tools"]],
            ["discover_docent_knowledge"],
        )

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_post_answer_discovery_emits_one_continuation_without_duplication(
        self,
        stream_request,
    ) -> None:
        captured_contexts = []

        def discover(context, _arguments):
            captured_contexts.append(context.model_copy(deep=True))
            return ToolExecutionResult(
                tool_name="discover_docent_knowledge",
                success=True,
                message="Discovery found.",
                data={"candidates": []},
            )

        registry = self._discovery_registry(discover)
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {"content": "Primary answer."},
                        "done": True,
                    }
                ]
            ),
            iter(
                [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "discover_docent_knowledge",
                                        "arguments": {
                                            "query": "an idea from the answer",
                                            "scope": "collection",
                                            "purpose": "proactive",
                                        },
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
                            "content": "One short continuation.",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "discover_docent_knowledge",
                                        "arguments": {
                                            "query": "try again",
                                            "scope": "collection",
                                            "purpose": "proactive",
                                        },
                                    }
                                }
                            ],
                        },
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Tell me about the artwork.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=registry,
            )
        )

        emitted_parts = [
            event.text
            for event in events
            if event.event_type == "content_delta"
        ]
        self.assertEqual(
            emitted_parts,
            ["Primary answer.", " One short continuation."],
        )
        self.assertEqual(emitted_parts.count("Primary answer."), 1)
        self.assertTrue(captured_contexts[0].visitor_sentence_emitted)
        self.assertEqual(
            captured_contexts[0].response_phase,
            "post_answer",
        )
        self.assertEqual(len(captured_contexts), 1)
        self.assertIsNone(stream_request.call_args_list[2].kwargs["tools"])
        self.assertIn(
            "at most one short natural continuation",
            stream_request.call_args_list[2].kwargs["messages"][-1]["content"],
        )
        self.assertIn(
            "return an empty response",
            stream_request.call_args_list[2].kwargs["messages"][-1]["content"],
        )

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_post_discovery_literal_no_additional_text_is_not_emitted(
        self,
        stream_request,
    ) -> None:
        registry = self._discovery_registry(
            lambda _context, _arguments: ToolExecutionResult(
                tool_name="discover_docent_knowledge",
                success=True,
                message="Discovery found.",
                data={"candidates": []},
            )
        )
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {"content": "Primary answer."},
                        "done": True,
                    }
                ]
            ),
            iter(
                [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "discover_docent_knowledge",
                                        "arguments": {
                                            "query": "related work",
                                            "scope": "collection",
                                            "purpose": "proactive",
                                        },
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
                        "message": {"content": "No additional text."},
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Tell me about the artwork.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=registry,
            )
        )

        emitted = "".join(
            event.text
            for event in events
            if event.event_type == "content_delta"
        )
        self.assertEqual(emitted, "Primary answer.")
        self.assertEqual(events[-1].event_type, "response_complete")
        self.assertEqual(events[-1].text, "")

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_post_discovery_control_block_is_not_emitted(
        self,
        stream_request,
    ) -> None:
        registry = self._discovery_registry(
            lambda _context, _arguments: ToolExecutionResult(
                tool_name="discover_docent_knowledge",
                success=True,
                message="Discovery found.",
                data={"candidates": []},
            )
        )
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {"content": "Primary answer."},
                        "done": True,
                    }
                ]
            ),
            iter(
                [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "discover_docent_knowledge",
                                        "arguments": {
                                            "query": "related work",
                                            "scope": "collection",
                                            "purpose": "proactive",
                                        },
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
                            "content": (
                                '<control>{"route_type":"response"}'
                                "</control> Actually, you might..."
                            )
                        },
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Tell me about the artwork.",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=registry,
            )
        )

        emitted_parts = [
            event.text
            for event in events
            if event.event_type == "content_delta"
        ]
        self.assertEqual(
            emitted_parts,
            ["Primary answer.", " Actually, you might..."],
        )
        self.assertNotIn(
            "<control>",
            "".join(emitted_parts),
        )

    @patch(
        "core_engine.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_delegated_discovery_remains_available_before_answer(
        self,
        stream_request,
    ) -> None:
        captured_contexts = []

        def discover(context, _arguments):
            captured_contexts.append(context.model_copy(deep=True))
            return ToolExecutionResult(
                tool_name="discover_docent_knowledge",
                success=True,
                message="Recommendation found.",
            )

        registry = self._discovery_registry(discover)
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "discover_docent_knowledge",
                                        "arguments": {
                                            "query": "what to see next",
                                            "scope": "collection",
                                            "purpose": "delegated",
                                        },
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
                        "message": {"content": "See The Swing next."},
                        "done": True,
                    }
                ]
            ),
        ]

        events = list(
            stream_tool_aware_llm_response(
                prompt="Which one is next?",
                conversation_id="conversation-a",
                buffer_for_tool_decision=False,
                tool_registry=registry,
            )
        )

        emitted = "".join(
            event.text
            for event in events
            if event.event_type == "content_delta"
        )
        self.assertEqual(emitted, "See The Swing next.")
        self.assertFalse(captured_contexts[0].visitor_sentence_emitted)
        self.assertEqual(
            captured_contexts[0].response_phase,
            "primary",
        )
        self.assertEqual(len(stream_request.call_args_list), 2)


if __name__ == "__main__":
    unittest.main()
