from __future__ import annotations

import unittest

from core_engine.api.routes_turn_buffer_stream import (
    build_stream_websocket_message,
)
from core_engine.schemas.control_signal_schemas import (
    ControlSignal,
)
from core_engine.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)


class DirectRoutingWebsocketTest(unittest.TestCase):
    def test_control_signal_has_a_dedicated_message(self) -> None:
        message = build_stream_websocket_message(
            request_id="request-control",
            event=LLMStreamEvent(
                event_type="control_signal",
                control_signal=ControlSignal(
                    route_type="backchannel"
                ),
            ),
        )

        self.assertEqual(
            message,
            {
                "type": "control_signal",
                "request_id": "request-control",
                "payload": {
                    "route_type": "backchannel",
                },
            },
        )

    def test_backend_tool_telemetry_is_not_sent_to_client(self) -> None:
        message = build_stream_websocket_message(
            request_id="request-tool",
            event=LLMStreamEvent(
                event_type="tool_result",
                tool_name="discover_docent_knowledge",
                tool_result={
                    "success": True,
                    "data": {"candidates": []},
                    "telemetry": {"raw_candidates": [{"rank": 1}]},
                },
            ),
        )

        self.assertNotIn("telemetry", message["payload"]["result"])
        self.assertEqual(
            message["payload"]["result"]["data"],
            {"candidates": []},
        )


if __name__ == "__main__":
    unittest.main()
