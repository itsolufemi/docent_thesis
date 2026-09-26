from __future__ import annotations

import unittest

from conversation_core.api.routes_turn_buffer_stream import (
    build_stream_websocket_message,
)
from conversation_core.schemas.control_signal_schemas import (
    ControlSignal,
)
from conversation_core.schemas.llm_stream_schemas import (
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


if __name__ == "__main__":
    unittest.main()
