import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from conversation_core.api.routes_turn_buffer_stream import (  # noqa: E402
    create_turn_buffer_stream_router,
)
from conversation_core.schemas.classifier_tool_schemas import (  # noqa: E402
    ClassifierToolAudit,
    ClassifierToolRoundResult,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    QueryResult,
)
from conversation_core.schemas.tool_schemas import (  # noqa: E402
    ToolExecutionContext,
    ToolExecutionResult,
)
from conversation_core.schemas.turn_buffer_schemas import (  # noqa: E402
    TurnBufferResult,
    TurnBufferState,
)
from conversation_core.schemas.utterance_route_schemas import (  # noqa: E402
    UtteranceRoute,
)
from conversation_core.services.classifier_tool_orchestration_service import (  # noqa: E402
    ClassifierToolProtocolError,
    run_required_classifier_tool_round,
)
from conversation_core.services.llm_service import (  # noqa: E402
    build_ollama_tool_definitions,
)
from conversation_core.tools.utterance_classifier_tool import (  # noqa: E402
    handle_classify_utterance,
)


def build_test_route() -> UtteranceRoute:
    return UtteranceRoute(
        route_type="response_request",
        floor_intent="take_floor",
        requires_retrieval=True,
        proposed_action=None,
        candidate_subjects=[
            "The Arab Tent"
        ],
        is_relevant=True,
        should_ignore=False,
        confidence=0.9,
        reason="Artwork information request.",
    )


def build_test_round_result(
) -> ClassifierToolRoundResult:
    return ClassifierToolRoundResult(
        utterance=(
            "Tell me about The Arab Tent."
        ),
        utterance_route=build_test_route(),
        audit=ClassifierToolAudit(
            classifier_call_count=1,
            classifier_called_exactly_once=True,
            classifier_omitted=False,
            classifier_called_more_than_once=False,
            invalid_classifier_arguments=False,
            model_returned_content=False,
            model_to_tool_call_seconds=0.5,
            classifier_execution_seconds=0.2,
            total_seconds=0.7,
        ),
        prompt="Mandatory classifier prompt.",
    )


class UtteranceClassifierToolTest(
    unittest.TestCase
):
    def test_tool_returns_route_data(
        self,
    ) -> None:
        result = handle_classify_utterance(
            ToolExecutionContext(
                conversation_id="conversation-1",
                assistant_was_speaking=True,
            ),
            {
                "utterance": (
                    "Tell me about The Arab Tent."
                ),
                "route_type": (
                    "response_request"
                ),
                "floor_intent": "take_floor",
                "requires_retrieval": True,
                "proposed_action": "none",
                "candidate_subjects": [
                    "The Arab Tent"
                ],
            },
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.tool_name,
            "classify_utterance",
        )
        self.assertEqual(
            result.data["utterance_route"][
                "route_type"
            ],
            "response_request",
        )
        self.assertEqual(
            result.data["utterance_route"][
                "candidate_subjects"
            ],
            ["The Arab Tent"],
        )
        self.assertIsNone(
            result.data["utterance_route"][
                "proposed_action"
            ]
        )

    def test_normal_tool_round_excludes_classifier(
        self,
    ) -> None:
        tool_names = {
            definition["function"]["name"]
            for definition
            in build_ollama_tool_definitions()
        }

        self.assertNotIn(
            "classify_utterance",
            tool_names,
        )


class ClassifierToolOrchestrationTest(
    unittest.TestCase
):
    @patch(
        "conversation_core.services."
        "classifier_tool_orchestration_service."
        "build_required_classifier_tool_prompt",
        return_value="Mandatory classifier prompt.",
    )
    @patch(
        "conversation_core.services."
        "classifier_tool_orchestration_service."
        "core_tool_registry.execute"
    )
    @patch(
        "conversation_core.services."
        "classifier_tool_orchestration_service."
        "collect_streamed_ollama_chat_response"
    )
    def test_first_round_exposes_only_classifier(
        self,
        send_request,
        execute_tool,
        _build_prompt,
    ) -> None:
        utterance = (
            "Tell me about The Arab Tent."
        )
        send_request.return_value = {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": (
                                "classify_utterance"
                            ),
                            "arguments": {
                                "utterance": utterance,
                                "route_type": (
                                    "response_request"
                                ),
                                "floor_intent": (
                                    "take_floor"
                                ),
                                "requires_retrieval": (
                                    True
                                ),
                                "proposed_action": (
                                    None
                                ),
                                "candidate_subjects": [
                                    "The Arab Tent"
                                ],
                            },
                        },
                    }
                ],
            }
        }
        execute_tool.return_value = (
            ToolExecutionResult(
                tool_name="classify_utterance",
                success=True,
                message="Classified.",
                data={
                    "utterance_route": (
                        build_test_route()
                        .model_dump(
                            mode="json"
                        )
                    ),
                },
            )
        )

        result = (
            run_required_classifier_tool_round(
                text=utterance,
                conversation_id="conversation-1",
            )
        )

        exposed_tools = (
            send_request.call_args.kwargs[
                "tools"
            ]
        )
        self.assertEqual(
            len(exposed_tools),
            1,
        )
        self.assertEqual(
            exposed_tools[0]["function"]["name"],
            "classify_utterance",
        )
        self.assertTrue(
            result.audit
            .classifier_called_exactly_once
        )
        self.assertFalse(
            result.audit.model_returned_content
        )
        self.assertEqual(
            result.utterance_route.route_type,
            "response_request",
        )

    @patch(
        "conversation_core.services."
        "classifier_tool_orchestration_service."
        "build_required_classifier_tool_prompt",
        return_value="Mandatory classifier prompt.",
    )
    @patch(
        "conversation_core.services."
        "classifier_tool_orchestration_service."
        "collect_streamed_ollama_chat_response",
        return_value={
            "message": {
                "content": "An answer without a tool.",
            }
        },
    )
    def test_omitted_classifier_is_recorded(
        self,
        _send_request,
        _build_prompt,
    ) -> None:
        with self.assertRaises(
            ClassifierToolProtocolError
        ) as error_context:
            run_required_classifier_tool_round(
                text="Hi, how are you?",
                conversation_id="conversation-1",
            )

        audit = error_context.exception.audit
        self.assertTrue(
            audit.classifier_omitted
        )
        self.assertTrue(
            audit.model_returned_content
        )


class ClassifierToolStreamCheckpointTest(
    unittest.TestCase
):
    @patch(
        "conversation_core.api."
        "routes_turn_buffer_stream."
        "process_turn_event"
    )
    def test_tool_result_resumes_response(
        self,
        process_turn_event,
    ) -> None:
        process_turn_event.return_value = (
            TurnBufferResult(
                state=TurnBufferState(
                    conversation_id=(
                        "conversation-test"
                    ),
                    transcript=(
                        "Tell me about "
                        "The Arab Tent."
                    ),
                    is_finalised=True,
                ),
                decision="finalise_turn",
                should_finalise_turn=True,
                finalised_utterance=(
                    "Tell me about "
                    "The Arab Tent."
                ),
                reason="Turn complete.",
            )
        )
        classifier_tool_runner = Mock(
            return_value=(
                build_test_round_result()
            )
        )
        query_engine = Mock()

        def generate_response(
            *,
            on_stream_event,
            **_,
        ):
            for event in [
                LLMStreamEvent(
                    event_type="response_started",
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="The Arab Tent ",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text=(
                        "The Arab Tent is..."
                    ),
                    done=True,
                ),
            ]:
                on_stream_event(event)

            return QueryResult(
                request=(
                    "Tell me about "
                    "The Arab Tent."
                ),
                response=(
                    "The Arab Tent is..."
                ),
                conversation_id=(
                    "conversation-test"
                ),
            )

        (
            query_engine
            .generate_classifier_tool_streaming_response
            .side_effect
        ) = generate_response
        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router(
                query_engine=query_engine,
                utterance_classifier=None,
                classifier_tool_runner=(
                    classifier_tool_runner
                ),
            )
        )

        with TestClient(app) as client:
            with client.websocket_connect(
                "/api/conversation/"
                "turn-buffer/stream"
            ) as websocket:
                ready = websocket.receive_json()
                websocket.send_json(
                    {
                        "type": "turn_event",
                        "request_id": "request-1",
                        "payload": {
                            "partial_utterance": (
                                "Tell me about "
                                "The Arab Tent."
                            ),
                            "is_speech_active": False,
                            "silence_duration_ms": 500,
                        },
                    }
                )
                messages = [
                    websocket.receive_json()
                    for _ in range(10)
                ]

        self.assertEqual(
            ready["type"],
            "turn_stream_ready",
        )
        self.assertEqual(
            [
                message["type"]
                for message in messages
            ],
            [
                "turn_evaluated",
                "classifier_tool_started",
                "utterance_classified",
                "classifier_tool_complete",
                "query_started",
                "response_started",
                "response_first_delta",
                "response_delta",
                "response_complete",
                "query_complete",
            ],
        )
        (
            query_engine
            .generate_classifier_tool_streaming_response
            .assert_called_once()
        )
        (
            query_engine
            .generate_streaming_response
            .assert_not_called()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
