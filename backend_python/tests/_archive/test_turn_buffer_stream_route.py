import sys
import time
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
                    event_type="timing",
                    timing_name=(
                        "context_resolution_seconds"
                    ),
                    timing_seconds=0.012,
                    timing_payload={
                        "context_source": (
                            "vector_retrieved_chunks"
                        ),
                    },
                ),
                LLMStreamEvent(
                    event_type="timing",
                    timing_name=(
                        "first_spoken_token_seconds"
                    ),
                    timing_seconds=1.75,
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
                websocket.close()

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
            cancellation_token=ANY,
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
        first_delta_message = next(
            message
            for message in messages
            if message["type"] == "response_first_delta"
        )
        self.assertEqual(
            first_delta_message["payload"]["timings"][0][
                "name"
            ],
            "context_resolution_seconds",
        )
        self.assertEqual(
            first_delta_message["payload"]["timings"][1][
                "name"
            ],
            "first_spoken_token_seconds",
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
                websocket.close()

        self.assertEqual(
            response["type"],
            "turn_error",
        )
        self.assertEqual(
            response["request_id"],
            "request-2",
        )

    @patch(
        "conversation_core.api.routes_turn_buffer_stream."
        "process_turn_event"
    )
    def test_cancel_turn_is_received_during_generation(
        self,
        process_turn_event,
    ) -> None:
        process_turn_event.return_value = TurnBufferResult(
            state=TurnBufferState(
                conversation_id="conversation-cancel",
                transcript="Tell me more.",
                is_finalised=True,
            ),
            decision="finalise_turn",
            should_finalise_turn=True,
            finalised_utterance="Tell me more.",
            reason="Turn complete.",
        )
        route = UtteranceRoute(
            route_type="response_request",
            floor_intent="take_floor",
            requires_retrieval=False,
            is_relevant=True,
            should_ignore=False,
            confidence=0.9,
            reason="A complete request.",
        )
        query_engine = Mock()

        def generate_until_cancelled(
            *,
            on_stream_event,
            cancellation_token,
            **_,
        ):
            on_stream_event(
                LLMStreamEvent(
                    event_type="response_started",
                )
            )
            on_stream_event(
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Partial response.",
                )
            )

            while not cancellation_token.is_cancelled:
                time.sleep(0.005)

            on_stream_event(
                LLMStreamEvent(
                    event_type="response_cancelled",
                    done=True,
                )
            )

            return QueryResult(
                request="Tell me more.",
                response="Partial response.",
                conversation_id=(
                    "conversation-cancel"
                ),
            )

        query_engine.generate_streaming_response.side_effect = (
            generate_until_cancelled
        )
        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router(
                query_engine=query_engine,
                utterance_classifier=Mock(
                    return_value=route,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/api/conversation/turn-buffer/stream"
            ) as websocket:
                websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "turn_event",
                        "request_id": "cancel-me",
                        "payload": {
                            "partial_utterance": (
                                "Tell me more."
                            ),
                            "is_speech_active": False,
                            "silence_duration_ms": 600,
                        },
                    }
                )

                received_types = []

                while "response_delta" not in received_types:
                    received_types.append(
                        websocket.receive_json()[
                            "type"
                        ]
                    )

                websocket.send_json(
                    {
                        "type": "cancel_turn",
                        "request_id": "cancel-me",
                    }
                )
                cancelled = websocket.receive_json()

                websocket.send_json(
                    {
                        "type": "unexpected",
                        "request_id": "after-cancel",
                    }
                )
                after_cancel = websocket.receive_json()
                websocket.close()

        self.assertEqual(
            cancelled["type"],
            "turn_cancelled",
        )
        self.assertEqual(
            cancelled["request_id"],
            "cancel-me",
        )
        self.assertEqual(
            after_cancel["type"],
            "turn_error",
        )

    @patch(
        "conversation_core.api."
        "routes_turn_buffer_stream."
        "append_telemetry_log"
    )
    @patch(
        "conversation_core.api."
        "routes_turn_buffer_stream."
        "process_turn_event"
    )
    def test_completed_turn_writes_backend_telemetry(
        self,
        process_turn_event,
        append_telemetry_log,
    ) -> None:
        process_turn_event.return_value = (
            TurnBufferResult(
                state=TurnBufferState(
                    conversation_id=(
                        "conversation-complete"
                    ),
                    transcript=(
                        "Tell me about The Swing."
                    ),
                    is_finalised=True,
                ),
                decision="finalise_turn",
                should_finalise_turn=True,
                finalised_utterance=(
                    "Tell me about The Swing."
                ),
                reason="Turn complete.",
            )
        )

        route = UtteranceRoute(
            route_type="response_request",
            floor_intent="take_floor",
            requires_retrieval=True,
            is_relevant=True,
            should_ignore=False,
            confidence=0.95,
            reason="Complete request.",
        )

        query_engine = Mock()

        def generate_streaming_response(
            *,
            on_stream_event,
            **_,
        ):
            on_stream_event(
                LLMStreamEvent(
                    event_type="timing",
                    timing_name=(
                        "context_resolution_seconds"
                    ),
                    timing_seconds=0.15,
                    timing_payload={
                        "context_source": (
                            "vector_retrieved_chunks"
                        ),
                        "source_count": 2,
                    },
                )
            )

            on_stream_event(
                LLMStreamEvent(
                    event_type="response_started",
                )
            )

            on_stream_event(
                LLMStreamEvent(
                    event_type="content_delta",
                    text="The Swing is ",
                )
            )

            on_stream_event(
                LLMStreamEvent(
                    event_type=(
                        "response_complete"
                    ),
                    text=(
                        "The Swing is by "
                        "Jean-Honoré Fragonard."
                    ),
                    done=True,
                )
            )

            return QueryResult(
                request=(
                    "Tell me about The Swing."
                ),
                response=(
                    "The Swing is by "
                    "Jean-Honoré Fragonard."
                ),
                conversation_id=(
                    "conversation-complete"
                ),
            )

        query_engine.generate_streaming_response.side_effect = (
            generate_streaming_response
        )

        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router(
                query_engine=query_engine,
                utterance_classifier=Mock(
                    return_value=route,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                (
                    "/api/conversation/"
                    "turn-buffer/stream"
                )
            ) as websocket:
                ready = (
                    websocket.receive_json()
                )

                conversation_id = (
                    ready["payload"][
                        "conversation_id"
                    ]
                )

                websocket.send_json(
                    {
                        "type": "turn_event",
                        "request_id": (
                            "request-complete"
                        ),
                        "payload": {
                            "partial_utterance": (
                                "Tell me about "
                                "The Swing."
                            ),
                            "is_speech_active": (
                                False
                            ),
                            "silence_duration_ms": (
                                600
                            ),
                            "debug": True,
                        },
                    }
                )

                message_type = None

                while (
                    message_type
                    != "query_complete"
                ):
                    message = (
                        websocket.receive_json()
                    )
                    message_type = (
                        message["type"]
                    )

        append_telemetry_log.assert_called_once()

        call = (
            append_telemetry_log.call_args
        )

        self.assertEqual(
            call.kwargs["conversation_id"],
            conversation_id,
        )
        self.assertEqual(
            call.kwargs["request_id"],
            "request-complete",
        )
        self.assertEqual(
            call.kwargs["event_type"],
            "backend_turn_complete",
        )

        payload = call.kwargs["payload"]

        self.assertEqual(
            payload["utterance"],
            "Tell me about The Swing.",
        )
        self.assertEqual(
            payload["utterance_route"][
                "route_type"
            ],
            "response_request",
        )
        self.assertEqual(
            len(payload["stream_timings"]),
            1,
        )
        self.assertEqual(
            payload["stream_timings"][0][
                "name"
            ],
            "context_resolution_seconds",
        )
        self.assertEqual(
            payload["query_result"][
                "response"
            ],
            (
                "The Swing is by "
                "Jean-Honoré Fragonard."
            ),
        )

    @patch(
        "conversation_core.api."
        "routes_turn_buffer_stream."
        "append_telemetry_log"
    )
    @patch(
        "conversation_core.api."
        "routes_turn_buffer_stream."
        "process_turn_event"
    )
    def test_cancelled_turn_writes_cancellation_telemetry(
        self,
        process_turn_event,
        append_telemetry_log,
    ) -> None:
        process_turn_event.return_value = (
            TurnBufferResult(
                state=TurnBufferState(
                    conversation_id=(
                        "conversation-cancelled"
                    ),
                    transcript="Tell me more.",
                    is_finalised=True,
                ),
                decision="finalise_turn",
                should_finalise_turn=True,
                finalised_utterance=(
                    "Tell me more."
                ),
                reason="Turn complete.",
            )
        )

        route = UtteranceRoute(
            route_type="response_request",
            floor_intent="take_floor",
            requires_retrieval=False,
            is_relevant=True,
            should_ignore=False,
            confidence=0.9,
            reason="Complete request.",
        )

        query_engine = Mock()

        def generate_until_cancelled(
            *,
            on_stream_event,
            cancellation_token,
            **_,
        ):
            on_stream_event(
                LLMStreamEvent(
                    event_type="response_started",
                )
            )

            on_stream_event(
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Partial response.",
                )
            )

            while (
                not cancellation_token
                .is_cancelled
            ):
                time.sleep(0.005)

            on_stream_event(
                LLMStreamEvent(
                    event_type=(
                        "response_cancelled"
                    ),
                    done=True,
                )
            )

            return QueryResult(
                request="Tell me more.",
                response="Partial response.",
                conversation_id=(
                    "conversation-cancelled"
                ),
            )

        query_engine.generate_streaming_response.side_effect = (
            generate_until_cancelled
        )

        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router(
                query_engine=query_engine,
                utterance_classifier=Mock(
                    return_value=route,
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                (
                    "/api/conversation/"
                    "turn-buffer/stream"
                )
            ) as websocket:
                ready = (
                    websocket.receive_json()
                )

                conversation_id = (
                    ready["payload"][
                        "conversation_id"
                    ]
                )

                websocket.send_json(
                    {
                        "type": "turn_event",
                        "request_id": (
                            "request-cancelled"
                        ),
                        "payload": {
                            "partial_utterance": (
                                "Tell me more."
                            ),
                            "is_speech_active": (
                                False
                            ),
                            "silence_duration_ms": (
                                600
                            ),
                        },
                    }
                )

                while True:
                    message = (
                        websocket.receive_json()
                    )

                    if (
                        message["type"]
                        == "response_delta"
                    ):
                        break

                websocket.send_json(
                    {
                        "type": "cancel_turn",
                        "request_id": (
                            "request-cancelled"
                        ),
                    }
                )

                cancelled_message = (
                    websocket.receive_json()
                )

        self.assertEqual(
            cancelled_message["type"],
            "turn_cancelled",
        )

        append_telemetry_log.assert_called_once()

        call = (
            append_telemetry_log.call_args
        )

        self.assertEqual(
            call.kwargs["conversation_id"],
            conversation_id,
        )
        self.assertEqual(
            call.kwargs["request_id"],
            "request-cancelled",
        )
        self.assertEqual(
            call.kwargs["event_type"],
            "backend_turn_cancelled",
        )
        self.assertEqual(
            call.kwargs["payload"][
                "utterance"
            ],
            "Tell me more.",
        )

    @patch(
        "conversation_core.api."
        "routes_turn_buffer_stream."
        "append_telemetry_log"
    )
    def test_client_telemetry_message_is_written(
        self,
        append_telemetry_log,
    ) -> None:
        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router()
        )

        telemetry_payload = {
            "voicePipelineFirstAudio": {
                "queryToFirstAudioSeconds": (
                    1.3268
                ),
            },
            "voicePipelinePlayback": {
                "queryToPlaybackSeconds": (
                    1.3364
                ),
            },
            "bufferUnderrunCount": 0,
        }

        with TestClient(app) as client:
            with client.websocket_connect(
                (
                    "/api/conversation/"
                    "turn-buffer/stream"
                )
            ) as websocket:
                ready = (
                    websocket.receive_json()
                )

                conversation_id = (
                    ready["payload"][
                        "conversation_id"
                    ]
                )

                websocket.send_json(
                    {
                        "type": (
                            "client_telemetry"
                        ),
                        "request_id": (
                            "request-client"
                        ),
                        "payload": (
                            telemetry_payload
                        ),
                    }
                )

                response = (
                    websocket.receive_json()
                )

        self.assertEqual(
            response["type"],
            "client_telemetry_recorded",
        )
        self.assertEqual(
            response["request_id"],
            "request-client",
        )

        append_telemetry_log.assert_called_once_with(
            conversation_id=conversation_id,
            request_id="request-client",
            event_type=(
                "client_voice_telemetry"
            ),
            payload=telemetry_payload,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
