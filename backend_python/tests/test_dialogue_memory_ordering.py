from __future__ import annotations

import sys
import unittest

from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent

for import_root in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


from conversation_core.memory.conversation_store import (  # noqa: E402
    conversations,
    create_conversation,
    get_recent_conversation_history,
    update_dialogue_turn_context,
)
from conversation_core.schemas.context_resolution_schemas import (  # noqa: E402
    ContextResolutionAssessment,
)
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    DialogueTurn,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    ResolvedContext,
)
from conversation_core.schemas.source_schemas import QuerySource  # noqa: E402
from conversation_core.services.prompt_service import (  # noqa: E402
    build_prompt,
    format_dialogue_history_for_prompt,
)
from conversation_core.services.query_service import QueryEngine  # noqa: E402
from conversation_core.schemas.prompt_schemas import PromptProfile  # noqa: E402
from docent.services.docent_query_service import (  # noqa: E402
    CONTEXT_RESOLUTION_INSTRUCTIONS,
)


def resolved_context(
    *,
    route_type: str = "response_request",
    subjects: list[str] | None = None,
    references: list[str] | None = None,
    is_relevant: bool = True,
) -> ResolvedContext:
    subjects = list(subjects or [])
    references = list(references or [])
    return ResolvedContext(
        context_source=(
            "subject_vector_retrieval"
            if references
            else "no_external_context"
        ),
        sources=[
            QuerySource(
                source_type="retrieved_chunk",
                reference=reference,
            )
            for reference in references
        ],
        prompt_payload={
            "subjects": subjects,
            "context_resolution": {
                "is_relevant": is_relevant,
                "route_type": route_type,
                "requires_retrieval": bool(references),
                "subjects": subjects,
            },
        },
        debug_payload={},
    )


class RecordingResolver:
    def __init__(self, resolutions: dict[str, ResolvedContext]) -> None:
        self.resolutions = resolutions
        self.snapshots: list[
            tuple[str, list[tuple[str | None, list[str], str | None, str | None]]]
        ] = []

    def __call__(self, history, text, utterance_route=None) -> ResolvedContext:
        self.snapshots.append(
            (
                text,
                [
                    (
                        turn.user,
                        list(turn.subject),
                        turn.route_type,
                        turn.assistant,
                    )
                    for turn in history
                ],
            )
        )
        return self.resolutions[text]


class PromptRecorder:
    def __init__(self) -> None:
        self.histories: list[list[DialogueTurn]] = []

    def __call__(self, text, history, resolved) -> str:
        self.histories.append(list(history))
        return f"Prompt for: {text}"


class ResponseRecorder:
    def __init__(self, response: str = "Response") -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, prompt: str, conversation_id: str | None) -> str:
        self.calls.append((prompt, conversation_id))
        return self.response


class DialogueMemoryOrderingTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()
        self.log_patch = patch(
            "conversation_core.memory.conversation_store."
            "append_dialogue_turn_log"
        )
        self.append_log = self.log_patch.start()

    def tearDown(self) -> None:
        self.log_patch.stop()
        conversations.clear()

    def test_context_route_label_is_potential_noise_only(self) -> None:
        assessment = ContextResolutionAssessment(
            is_relevant=False,
            route_type="potential_noise",
            requires_retrieval=False,
            subjects=[],
        )
        self.assertEqual(assessment.route_type, "potential_noise")

        with self.assertRaises(ValidationError):
            ContextResolutionAssessment(
                is_relevant=False,
                route_type="noise",
                requires_retrieval=False,
                subjects=[],
            )

        self.assertIn(
            "backchannel, or potential_noise",
            CONTEXT_RESOLUTION_INSTRUCTIONS,
        )
        self.assertIn(
            "potential_noise:",
            CONTEXT_RESOLUTION_INSTRUCTIONS,
        )

    def test_existing_turn_is_enriched_in_place(self) -> None:
        state = create_conversation()
        turn = DialogueTurn(user="I am looking at The Rising of the Sun.")
        state.dialogue_history.append(turn)

        updated = update_dialogue_turn_context(
            state.conversation_id,
            turn,
            subject=["The Rising of the Sun"],
            reference=["painting:118"],
            route_type="response_request",
        )

        self.assertIs(updated, turn)
        self.assertIs(state.dialogue_history[0], turn)
        self.assertEqual(turn.subject, ["The Rising of the Sun"])
        self.assertEqual(turn.reference, ["painting:118"])
        self.assertEqual(turn.route_type, "response_request")

    def test_p03_second_resolver_sees_first_pending_utterance(self) -> None:
        state = create_conversation()
        first_started = Event()
        release_first = Event()
        snapshots: dict[str, list[tuple[str | None, list[str]]]] = {}
        thread_errors: list[BaseException] = []

        def resolver(history, text, utterance_route=None):
            snapshots[text] = [
                (turn.user, list(turn.subject))
                for turn in history
            ]
            if text.startswith("I'm now looking"):
                first_started.set()
                if not release_first.wait(timeout=5):
                    raise TimeoutError("First resolver was not released.")
                return resolved_context(
                    subjects=["The Rising of the Sun"]
                )
            return resolved_context(
                subjects=["The Rising of the Sun"]
            )

        engine = QueryEngine(
            subject_resolver=resolver,
            prompt_builder=PromptRecorder(),
            response_generator=ResponseRecorder(),
        )
        first_text = "I'm now looking at The Rising of the Sun."
        second_text = (
            "and can you just give me a general overview of what it is?"
        )

        def run_first() -> None:
            try:
                engine.generate_response(
                    first_text,
                    conversation_id=state.conversation_id,
                )
            except BaseException as error:
                thread_errors.append(error)

        first_thread = Thread(target=run_first)
        first_thread.start()
        self.assertTrue(first_started.wait(timeout=5))

        engine.generate_response(
            second_text,
            conversation_id=state.conversation_id,
        )

        self.assertEqual(
            snapshots[second_text],
            [(first_text, [])],
        )

        release_first.set()
        first_thread.join(timeout=5)
        self.assertFalse(first_thread.is_alive())
        self.assertEqual(thread_errors, [])

    def test_cancelled_stream_preserves_subject_and_marks_interrupted(self) -> None:
        text = "I'm now looking at The Rising of the Sun."
        engine = QueryEngine(
            subject_resolver=RecordingResolver(
                {
                    text: resolved_context(
                        subjects=["The Rising of the Sun"],
                        references=["painting:118"],
                    )
                }
            ),
            prompt_builder=PromptRecorder(),
        )

        def cancelled_stream(**kwargs):
            yield LLMStreamEvent(
                event_type="content_delta",
                text="The painting begins",
            )
            yield LLMStreamEvent(
                event_type="response_cancelled",
                done=True,
            )

        with patch(
            "conversation_core.services.query_service.stream_llm_response",
            side_effect=cancelled_stream,
        ):
            result = engine.generate_streaming_response(text)

        history = get_recent_conversation_history(result.conversation_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].subject, ["The Rising of the Sun"])
        self.assertEqual(history[0].reference, ["painting:118"])
        self.assertEqual(history[0].route_type, "response_request")
        self.assertEqual(history[0].assistant, "[interrupted]")
        self.append_log.assert_called_once()

    def test_potential_noise_survives_and_is_visible_to_later_resolution(self) -> None:
        first = "There's a mountain, a few trees and some sparsely."
        fragment = "populated fields. Is this known to be set anywhere?"
        follow_up = "What does that landscape tell us?"
        resolver = RecordingResolver(
            {
                first: resolved_context(),
                fragment: resolved_context(
                    route_type="potential_noise",
                    is_relevant=False,
                ),
                follow_up: resolved_context(),
            }
        )
        responses = ResponseRecorder()
        engine = QueryEngine(
            subject_resolver=resolver,
            prompt_builder=PromptRecorder(),
            response_generator=responses,
        )

        first_result = engine.generate_response(first)
        suppressed = engine.generate_response(
            fragment,
            conversation_id=first_result.conversation_id,
        )
        engine.generate_response(
            follow_up,
            conversation_id=first_result.conversation_id,
        )

        self.assertEqual(suppressed.response, "")
        self.assertEqual(len(responses.calls), 2)
        history = get_recent_conversation_history(first_result.conversation_id)
        self.assertEqual(history[1].user, fragment)
        self.assertEqual(history[1].route_type, "potential_noise")
        self.assertIsNone(history[1].assistant)
        self.assertIn(
            f"User [potential noise]: {fragment}",
            format_dialogue_history_for_prompt(history),
        )
        self.assertEqual(
            resolver.snapshots[2][1][1],
            (fragment, [], "potential_noise", None),
        )

    def test_diana_follow_up_sees_interrupted_assistant_turn(self) -> None:
        first = "Is Diana scared of Venus?"
        second = "Or is she just surprised in the painting?"
        resolver = RecordingResolver(
            {
                first: resolved_context(subjects=["Diana and Venus"]),
                second: resolved_context(subjects=["Diana and Venus"]),
            }
        )
        engine = QueryEngine(
            subject_resolver=resolver,
            prompt_builder=PromptRecorder(),
            response_generator=ResponseRecorder(),
        )

        def cancelled_stream(**kwargs):
            yield LLMStreamEvent(
                event_type="response_cancelled",
                done=True,
            )

        with patch(
            "conversation_core.services.query_service.stream_llm_response",
            side_effect=cancelled_stream,
        ):
            first_result = engine.generate_streaming_response(first)

        engine.generate_response(
            second,
            conversation_id=first_result.conversation_id,
        )

        self.assertEqual(
            resolver.snapshots[1][1],
            [
                (
                    first,
                    ["Diana and Venus"],
                    "response_request",
                    "[interrupted]",
                )
            ],
        )

    def test_backchannel_is_suppressed_but_preserved(self) -> None:
        text = "Mm-hm."
        responses = ResponseRecorder()
        engine = QueryEngine(
            subject_resolver=RecordingResolver(
                {
                    text: resolved_context(
                        route_type="backchannel",
                    )
                }
            ),
            prompt_builder=PromptRecorder(),
            response_generator=responses,
        )

        result = engine.generate_response(text)
        history = get_recent_conversation_history(result.conversation_id)

        self.assertEqual(result.response, "")
        self.assertEqual(responses.calls, [])
        self.assertEqual(history[0].route_type, "backchannel")
        self.assertIsNone(history[0].assistant)
        self.assertIn(
            "User [backchannel]: Mm-hm.",
            format_dialogue_history_for_prompt(history),
        )

    def test_response_prompt_explains_history_labels_as_metadata(self) -> None:
        profile = PromptProfile(
            assistant_name="Docent",
            user_name="Visitor",
            assistant_role="You are Docent.",
        )
        prompt = build_prompt(
            user_input="Could that fragment matter?",
            dialogue_history=[
                DialogueTurn(
                    user="populated fields.",
                    route_type="potential_noise",
                )
            ],
            profile=profile,
        )

        self.assertIn(
            "Visitor [potential noise]: populated fields.",
            prompt,
        )
        self.assertIn(
            "Treat them as contextual\nmetadata rather than guaranteed facts.",
            prompt,
        )
        self.assertIn(
            "Later dialogue may make an earlier\nutterance more meaningful.",
            prompt,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
