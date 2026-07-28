import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.api.routes_turn_buffer_stream import (
    create_turn_buffer_stream_router,
)
from conversation_core.schemas.query_schemas import QueryResult
from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)
from conversation_core.schemas.turn_buffer_schemas import (
    TurnBufferResult,
    TurnBufferState,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)


class TurnBufferStreamRouteTest(unittest.TestCase):
    @patch(
        "conversation_core.api.routes_turn_buffer_stream."
        "process_turn_event"
    )
    def test_classification_arrives_before_query_completion(
        self,
        process_turn_event,
    ) -> None:
        process_turn_event.return_value = TurnBufferResult(
            state=TurnBufferState(
                conversation_id="conversation-test",
                transcript="Wait, when was it painted?",
                is_finalised=True,
            ),
            decision="finalise_turn",
            should_finalise_turn=True,
            finalised_utterance=(
                "Wait, when was it painted?"
            ),
            reason="Turn complete.",
        )
        utterance_route = UtteranceRoute(
            route_type="response_request",
            floor_intent="take_floor",
            requires_retrieval=True,
            is_relevant=True,
            should_ignore=False,
            confidence=0.96,
            reason="The user takes the floor.",
        )
        classifier = Mock(
            return_value=utterance_route,
        )
        query_engine = Mock()

        def generate_streaming_response(
            *,
            on_stream_event,
            **_,
        ):
            for event in (
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="It was ",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="painted around 1767.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="It was painted around 1767.",
                    done=True,
                ),
            ):
                on_stream_event(event)

            return QueryResult(
                request="Wait, when was it painted?",
                response="It was painted around 1767.",
                conversation_id="conversation-test",
            )

        query_engine.generate_streaming_response.side_effect = (
            generate_streaming_response
        )

        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router(
                query_engine=query_engine,
                utterance_classifier=classifier,
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/api/conversation/turn-buffer/stream"
            ) as websocket:
                ready = websocket.receive_json()
                conversation_id = ready["payload"][
                    "conversation_id"
                ]

                websocket.send_json(
                    {
                        "type": "turn_event",
                        "request_id": "request-1",
                        "payload": {
                            "partial_utterance": (
                                "Wait, when was it painted?"
                            ),
                            "is_speech_active": False,
                            "silence_duration_ms": 600,
                            "assistant_was_speaking": True,
                            "debug": True,
                        },
                    }
                )

                messages = [
                    websocket.receive_json()
                    for _ in range(9)
                ]

        self.assertEqual(
            ready["type"],
            "turn_stream_ready",
        )
        self.assertEqual(
            [message["type"] for message in messages],
            [
                "turn_evaluated",
                "utterance_classified",
                "query_started",
                "response_started",
                "response_first_delta",
                "response_delta",
                "response_delta",
                "response_complete",
                "query_complete",
            ],
        )
        self.assertEqual(
            messages[1]["payload"]["floor_intent"],
            "take_floor",
        )
        classifier.assert_called_once_with(
            "Wait, when was it painted?",
            True,
        )
        query_engine.generate_streaming_response.assert_called_once_with(
            text="Wait, when was it painted?",
            conversation_id=conversation_id,
            subject_reference=None,
            utterance_route=utterance_route,
            include_debug=True,
            on_stream_event=ANY,
        )
        streamed_text = "".join(
            message["payload"]["text"]
            for message in messages
            if message["type"] == "response_delta"
        )
        self.assertEqual(
            streamed_text,
            messages[-1]["payload"]["response"],
        )

    def test_invalid_message_type_returns_turn_error(
        self,
    ) -> None:
        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router()
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/api/conversation/turn-buffer/stream"
            ) as websocket:
                websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "unexpected",
                        "request_id": "request-2",
                    }
                )
                response = websocket.receive_json()

        self.assertEqual(
            response["type"],
            "turn_error",
        )
        self.assertEqual(
            response["request_id"],
            "request-2",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
