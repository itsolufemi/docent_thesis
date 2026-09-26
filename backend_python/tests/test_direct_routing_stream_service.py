from __future__ import annotations

import unittest

from unittest.mock import patch

from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)
from conversation_core.services.direct_routing_stream_service import (
    stream_direct_routed_response,
)


class DirectRoutingStreamServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.direct_routing_stream_service."
        "stream_tool_aware_llm_response"
    )
    def test_normal_content_streams_unchanged(self, stream_llm) -> None:
        stream_llm.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Hello",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=" there.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Hello there.",
                    done=True,
                ),
            ]
        )

        events = list(
            stream_direct_routed_response(
                "prompt",
                "conversation-a",
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
            "Hello there.",
        )

    @patch(
        "conversation_core.services.direct_routing_stream_service."
        "stream_tool_aware_llm_response"
    )
    def test_split_control_emits_one_typed_event(self, stream_llm) -> None:
        stream_llm.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="<con",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "trol>{\"route_type\":\"backchannel\"}"
                        "</control>"
                    ),
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="internal control",
                    done=True,
                ),
            ]
        )

        events = list(
            stream_direct_routed_response(
                "prompt",
                "conversation-b",
            )
        )

        self.assertEqual(
            [event.event_type for event in events],
            ["response_started", "control_signal"],
        )
        self.assertEqual(
            events[-1].control_signal.route_type,
            "backchannel",
        )

    @patch(
        "conversation_core.services.direct_routing_stream_service."
        "stream_tool_aware_llm_response"
    )
    def test_tool_events_pass_through(self, stream_llm) -> None:
        stream_llm.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="tool_call",
                    tool_calls=[{"name": "retrieve"}],
                ),
                LLMStreamEvent(
                    event_type="tool_result",
                    tool_name="retrieve",
                    tool_result={"success": True},
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Answer.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Answer.",
                    done=True,
                ),
            ]
        )

        events = list(
            stream_direct_routed_response(
                "prompt",
                "conversation-c",
            )
        )

        self.assertEqual(
            [event.event_type for event in events],
            [
                "response_started",
                "tool_call",
                "tool_result",
                "content_delta",
                "response_complete",
            ],
        )


if __name__ == "__main__":
    unittest.main()
