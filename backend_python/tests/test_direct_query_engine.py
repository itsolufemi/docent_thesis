from __future__ import annotations

import sys
import unittest

from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    add_dialogue_turn,
    build_history_with_playback_interruption,
    conversations,
    create_conversation,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.schemas.source_schemas import QuerySource  # noqa: E402
from conversation_core.schemas.tool_schemas import (  # noqa: E402
    ToolDialogueStateUpdate,
    ToolExecutionResult,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)
from docent.services.docent_query_service import (  # noqa: E402
    docent_build_direct_prompt,
)
from docent.tools import docent_tool_registry  # noqa: E402


class DirectQueryEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()
        self.state = create_conversation()

    def tearDown(self) -> None:
        conversations.clear()

    def _engine(self) -> QueryEngine:
        return QueryEngine(
            subject_resolver=None,
            prompt_builder=docent_build_direct_prompt,
            direct_routing_enabled=True,
            tool_registry=docent_tool_registry,
        )

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_normal_response_skips_subject_resolver(self, stream) -> None:
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Hello there.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Hello there.",
                    done=True,
                ),
            ]
        )

        result = self._engine().generate_streaming_response(
            "Hello.",
            conversation_id=self.state.conversation_id,
            include_debug=True,
        )

        self.assertEqual(result.response, "Hello there.")
        self.assertEqual(
            result.debug.context_source,
            "direct_routing",
        )
        self.assertEqual(
            self.state.dialogue_history[-1].assistant,
            "Hello there.",
        )
        stream.assert_called_once()
        self.assertIs(
            stream.call_args.kwargs["tool_registry"],
            docent_tool_registry,
        )

    def test_non_direct_engine_still_requires_resolver(self) -> None:
        with self.assertRaises(ValueError):
            QueryEngine(
                subject_resolver=None,
                prompt_builder=docent_build_direct_prompt,
            )

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_tool_result_enriches_turn_before_answer(self, stream) -> None:
        tool_result = ToolExecutionResult(
            tool_name="retrieve_docent_knowledge",
            success=True,
            message="Retrieved.",
            dialogue_state=ToolDialogueStateUpdate(
                subjects=["The Swing"],
                references=["painting:581"],
            ),
            sources=[
                QuerySource(
                    source_type="retrieved_chunk",
                    title="The Swing",
                    reference="painting:581",
                )
            ],
        )
        snapshots = []

        def events():
            yield LLMStreamEvent(event_type="response_started")
            yield LLMStreamEvent(
                event_type="tool_call",
                tool_calls=[
                    {
                        "name": "retrieve_docent_knowledge",
                        "arguments": {"subjects": ["The Swing"]},
                    }
                ],
            )
            yield LLMStreamEvent(
                event_type="tool_result",
                tool_name="retrieve_docent_knowledge",
                tool_result=tool_result.model_dump(mode="json"),
            )
            snapshots.append(
                self.state.dialogue_history[-1].model_copy(deep=True)
            )
            yield LLMStreamEvent(
                event_type="content_delta",
                text="Fragonard painted it.",
            )
            yield LLMStreamEvent(
                event_type="response_complete",
                text="Fragonard painted it.",
                done=True,
            )

        stream.return_value = events()

        result = self._engine().generate_streaming_response(
            "Who painted The Swing?",
            conversation_id=self.state.conversation_id,
        )

        self.assertEqual(snapshots[0].subject, ["The Swing"])
        self.assertEqual(snapshots[0].reference, ["painting:581"])
        self.assertEqual(result.sources[0].reference, "painting:581")

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_backchannel_preserves_previous_assistant(self, stream) -> None:
        previous = add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            user="Tell me about The Swing.",
            assistant="A. B. C.",
        )
        override = build_history_with_playback_interruption(
            [previous],
            request_id="request-a",
            assistant_text="A. [interrupted]",
        )
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="control_signal",
                    control_signal={"route_type": "backchannel"},
                ),
            ]
        )

        result = self._engine().generate_streaming_response(
            "Mm-hm.",
            conversation_id=self.state.conversation_id,
            dialogue_history_override=override,
            interrupted_request_id="request-a",
            interrupted_assistant_text="A. [interrupted]",
        )

        current = self.state.dialogue_history[-1]
        self.assertEqual(result.response, "")
        self.assertEqual(previous.assistant, "A. B. C.")
        self.assertEqual(current.route_type, "backchannel")
        self.assertEqual(current.subject, ["The Swing"])

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_interruption_commits_previous_playback(self, stream) -> None:
        previous = add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            user="Tell me about The Swing.",
            assistant="A. B. C.",
        )
        override = build_history_with_playback_interruption(
            [previous],
            request_id="request-a",
            assistant_text="A. [interrupted]",
        )
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="control_signal",
                    control_signal={"route_type": "interruption"},
                ),
            ]
        )

        self._engine().generate_streaming_response(
            "Wait.",
            conversation_id=self.state.conversation_id,
            dialogue_history_override=override,
            interrupted_request_id="request-a",
            interrupted_assistant_text="A. [interrupted]",
        )

        self.assertEqual(previous.assistant, "A. [interrupted]")
        self.assertEqual(
            self.state.dialogue_history[-1].route_type,
            "interruption",
        )

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_potential_noise_preserves_previous_assistant(self, stream) -> None:
        previous = add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            user="Tell me about The Swing.",
            assistant="A. B. C.",
        )
        override = build_history_with_playback_interruption(
            [previous],
            request_id="request-a",
            assistant_text="A. [interrupted]",
        )
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="control_signal",
                    control_signal={"route_type": "potential_noise"},
                ),
            ]
        )

        self._engine().generate_streaming_response(
            "[background noise]",
            conversation_id=self.state.conversation_id,
            dialogue_history_override=override,
            interrupted_request_id="request-a",
            interrupted_assistant_text="A. [interrupted]",
        )

        current = self.state.dialogue_history[-1]
        self.assertEqual(previous.assistant, "A. B. C.")
        self.assertEqual(current.route_type, "potential_noise")
        self.assertEqual(current.subject, [])

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_tool_call_commits_interruption_before_execution_result(
        self,
        stream,
    ) -> None:
        previous = add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            user="Tell me about The Swing.",
            assistant="A. B. C.",
        )
        override = build_history_with_playback_interruption(
            [previous],
            request_id="request-a",
            assistant_text="A. [interrupted]",
        )
        observed_assistant_text = []

        def events():
            yield LLMStreamEvent(event_type="response_started")
            yield LLMStreamEvent(
                event_type="tool_call",
                tool_calls=[
                    {
                        "name": "retrieve_docent_knowledge",
                        "arguments": {"subjects": ["The Swing"]},
                    }
                ],
            )
            observed_assistant_text.append(previous.assistant)
            yield LLMStreamEvent(
                event_type="content_delta",
                text="Answer.",
            )
            yield LLMStreamEvent(
                event_type="response_complete",
                text="Answer.",
                done=True,
            )

        stream.return_value = events()

        self._engine().generate_streaming_response(
            "Who painted it?",
            conversation_id=self.state.conversation_id,
            dialogue_history_override=override,
            interrupted_request_id="request-a",
            interrupted_assistant_text="A. [interrupted]",
        )

        self.assertEqual(
            observed_assistant_text,
            ["A. [interrupted]"],
        )

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_normal_response_commits_previous_playback(self, stream) -> None:
        previous = add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            user="Tell me about The Swing.",
            assistant="A. B. C.",
        )
        override = build_history_with_playback_interruption(
            [previous],
            request_id="request-a",
            assistant_text="A. [interrupted]",
        )
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="I meant the other work.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="I meant the other work.",
                    done=True,
                ),
            ]
        )

        self._engine().generate_streaming_response(
            "No, the other painting.",
            conversation_id=self.state.conversation_id,
            dialogue_history_override=override,
            interrupted_request_id="request-a",
            interrupted_assistant_text="A. [interrupted]",
        )

        self.assertEqual(previous.assistant, "A. [interrupted]")

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_reference_history_reaches_the_direct_model(self, stream) -> None:
        add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            reference=["painting:581"],
            user="Tell me about The Swing.",
            assistant="It was painted by Fragonard.",
        )
        tool_result = ToolExecutionResult(
            tool_name="retrieve_docent_knowledge",
            success=True,
            message="Retrieved.",
            dialogue_state=ToolDialogueStateUpdate(
                subjects=["The Swing"],
                references=["painting:581"],
            ),
        )
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="tool_call",
                    tool_calls=[
                        {
                            "name": "retrieve_docent_knowledge",
                            "arguments": {
                                "subjects": ["The Swing"],
                            },
                        }
                    ],
                ),
                LLMStreamEvent(
                    event_type="tool_result",
                    tool_name="retrieve_docent_knowledge",
                    tool_result=tool_result.model_dump(mode="json"),
                ),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Fragonard painted it.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Fragonard painted it.",
                    done=True,
                ),
            ]
        )

        self._engine().generate_streaming_response(
            "Who painted it?",
            conversation_id=self.state.conversation_id,
        )

        prompt = stream.call_args.kwargs["prompt"]
        self.assertIn("Subjects: ['The Swing']", prompt)
        self.assertIn("Visitor: Who painted it?", prompt)
        current = self.state.dialogue_history[-1]
        self.assertEqual(current.subject, ["The Swing"])
        self.assertEqual(current.reference, ["painting:581"])

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_two_turn_interruption_then_correction(self, stream) -> None:
        previous = add_dialogue_turn(
            self.state.conversation_id,
            request_id="request-a",
            subject=["The Swing"],
            user="Tell me about The Swing.",
            assistant="A. B. C.",
        )
        override = build_history_with_playback_interruption(
            [previous],
            request_id="request-a",
            assistant_text="A. [interrupted]",
        )
        stream.side_effect = [
            iter(
                [
                    LLMStreamEvent(event_type="response_started"),
                    LLMStreamEvent(
                        event_type="control_signal",
                        control_signal={"route_type": "interruption"},
                    ),
                ]
            ),
            iter(
                [
                    LLMStreamEvent(event_type="response_started"),
                    LLMStreamEvent(
                        event_type="content_delta",
                        text="You mean the other painting.",
                    ),
                    LLMStreamEvent(
                        event_type="response_complete",
                        text="You mean the other painting.",
                        done=True,
                    ),
                ]
            ),
        ]
        engine = self._engine()

        engine.generate_streaming_response(
            "Wait.",
            conversation_id=self.state.conversation_id,
            dialogue_history_override=override,
            interrupted_request_id="request-a",
            interrupted_assistant_text="A. [interrupted]",
        )
        result = engine.generate_streaming_response(
            "No, I meant the other painting.",
            conversation_id=self.state.conversation_id,
        )

        second_prompt = stream.call_args_list[1].kwargs["prompt"]
        self.assertIn("Visitor [interruption]: Wait.", second_prompt)
        self.assertEqual(previous.assistant, "A. [interrupted]")
        self.assertEqual(
            result.response,
            "You mean the other painting.",
        )
        self.assertIsNone(self.state.dialogue_history[-1].route_type)

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_unmatched_call_to_action_stays_conversational(
        self,
        stream,
    ) -> None:
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="content_delta",
                    text=(
                        "I can't move the painting, but I can tell you "
                        "about it."
                    ),
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text=(
                        "I can't move the painting, but I can tell you "
                        "about it."
                    ),
                    done=True,
                ),
            ]
        )

        result = self._engine().generate_streaming_response(
            "Move that painting to another room.",
            conversation_id=self.state.conversation_id,
        )

        self.assertIn("can't move", result.response)
        current = self.state.dialogue_history[-1]
        self.assertEqual(current.subject, [])
        self.assertIsNone(current.route_type)


if __name__ == "__main__":
    unittest.main()
