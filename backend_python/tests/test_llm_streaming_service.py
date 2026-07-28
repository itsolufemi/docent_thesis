import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.services.llm_service import (
    stream_tool_aware_llm_response,
)


class LlmStreamingServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_ordinary_response_streams_each_delta(
        self,
        stream_request,
    ) -> None:
        stream_request.return_value = iter(
            [
                {
                    "message": {
                        "content": "The Swing ",
                    },
                    "done": False,
                },
                {
                    "message": {
                        "content": "was painted in 1767.",
                    },
                    "done": True,
                },
            ]
        )

        events = list(
            stream_tool_aware_llm_response(
                prompt="Tell me about The Swing.",
                conversation_id="conversation-1",
                buffer_for_tool_decision=False,
            )
        )

        self.assertEqual(
            [event.event_type for event in events],
            [
                "response_started",
                "content_delta",
                "content_delta",
                "response_complete",
            ],
        )
        self.assertEqual(
            "".join(
                event.text
                for event in events
                if event.event_type == "content_delta"
            ),
            "The Swing was painted in 1767.",
        )

    @patch(
        "conversation_core.services.llm_service."
        "core_tool_registry.execute"
    )
    @patch(
        "conversation_core.services.llm_service."
        "stream_ollama_chat_request"
    )
    def test_action_buffers_tool_round_then_streams_answer(
        self,
        stream_request,
        execute_tool,
    ) -> None:
        stream_request.side_effect = [
            iter(
                [
                    {
                        "message": {
                            "content": (
                                "Internal tool planning."
                            ),
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "test_tool",
                                        "arguments": {},
                                    },
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
                            "content": "The tour ",
                        },
                        "done": False,
                    },
                    {
                        "message": {
                            "content": "has started.",
                        },
                        "done": True,
                    },
                ]
            ),
        ]
        execution_result = Mock()
        execution_result.model_dump.return_value = {
            "success": True,
        }
        execution_result.model_dump_json.return_value = (
            '{"success": true}'
        )
        execute_tool.return_value = execution_result

        events = list(
            stream_tool_aware_llm_response(
                prompt="Start a highlights tour.",
                conversation_id="conversation-2",
                buffer_for_tool_decision=True,
            )
        )

        event_types = [
            event.event_type
            for event in events
        ]
        self.assertEqual(
            event_types,
            [
                "response_started",
                "tool_call",
                "tool_result",
                "content_delta",
                "content_delta",
                "response_complete",
            ],
        )
        visible_text = "".join(
            event.text
            for event in events
            if event.event_type == "content_delta"
        )
        self.assertEqual(
            visible_text,
            "The tour has started.",
        )
        self.assertNotIn(
            "Internal tool planning.",
            visible_text,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
