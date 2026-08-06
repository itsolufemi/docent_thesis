import sys
from pathlib import Path


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    conversations,
    get_recent_conversation_history,
)
from conversation_core.schemas.query_schemas import (  # noqa: E402
    ResolvedContext,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)


class FakeResolver:
    def __init__(
        self,
        *,
        subjects: list[str] | None = None,
        context_source: str = "no_external_context",
    ) -> None:
        self.subjects = subjects or []
        self.context_source = context_source
        self.calls: list[tuple[list, str, object]] = []

    def __call__(
        self,
        dialogue_history,
        user_input,
        utterance_route=None,
    ) -> ResolvedContext:
        self.calls.append(
            (
                list(dialogue_history),
                user_input,
                utterance_route,
            )
        )
        return ResolvedContext(
            context_source=self.context_source,
            prompt_payload={
                "subjects": list(self.subjects),
                "context_resolution": {
                    "is_relevant": True,
                    "route_type": "response_request",
                    "requires_retrieval": bool(
                        self.subjects
                    ),
                    "subjects": list(self.subjects),
                },
            },
            debug_payload={
                "context_resolution": {
                    "is_relevant": True,
                    "route_type": "response_request",
                    "requires_retrieval": bool(
                        self.subjects
                    ),
                    "subjects": list(self.subjects),
                }
            },
        )


class FakePromptBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list, ResolvedContext]] = []

    def __call__(
        self,
        user_input,
        dialogue_history,
        resolved_context,
    ) -> str:
        self.calls.append(
            (
                user_input,
                list(dialogue_history),
                resolved_context,
            )
        )
        return f"Prompt for: {user_input}"


class FakeResponseGenerator:
    def __init__(self, response: str = "response") -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    def __call__(
        self,
        prompt,
        conversation_id,
    ) -> str:
        self.calls.append((prompt, conversation_id))
        return self.response


def setup_function() -> None:
    conversations.clear()


def test_generate_response_uses_context_resolver_and_stores_subject_list():
    resolver = FakeResolver(
        subjects=[
            "The Arab Tent",
            "The Rising of the Sun",
        ],
        context_source="subject_vector_retrieval",
    )
    prompt_builder = FakePromptBuilder()
    response_generator = FakeResponseGenerator(
        "They differ in subject and treatment."
    )
    engine = QueryEngine(
        subject_resolver=resolver,
        prompt_builder=prompt_builder,
        response_generator=response_generator,
    )

    result = engine.generate_response(
        text=(
            "Compare The Arab Tent and "
            "The Rising of the Sun."
        ),
        include_debug=True,
    )

    assert result.response == (
        "They differ in subject and treatment."
    )
    assert result.subject_reference is None
    assert len(resolver.calls) == 1
    assert resolver.calls[0][0] == []
    assert resolver.calls[0][1] == (
        "Compare The Arab Tent and "
        "The Rising of the Sun."
    )

    history = get_recent_conversation_history(
        conversation_id=result.conversation_id,
    )
    assert [turn.role for turn in history] == [
        "user",
        "assistant",
    ]
    assert history[0].subjects == [
        "The Arab Tent",
        "The Rising of the Sun",
    ]
    assert history[1].subjects == [
        "The Arab Tent",
        "The Rising of the Sun",
    ]

    assert result.debug is not None
    assert result.debug.retrieval_used is True
    assert result.debug.debug_payload["subjects"] == [
        "The Arab Tent",
        "The Rising of the Sun",
    ]


def test_follow_up_passes_existing_dialogue_to_context_resolver():
    resolver = FakeResolver(subjects=["The Arab Tent"])
    engine = QueryEngine(
        subject_resolver=resolver,
        prompt_builder=FakePromptBuilder(),
        response_generator=FakeResponseGenerator(),
    )

    first = engine.generate_response(
        text="Tell me about The Arab Tent."
    )
    engine.generate_response(
        text="Who painted it?",
        conversation_id=first.conversation_id,
    )

    assert len(resolver.calls) == 2
    second_history = resolver.calls[1][0]
    assert [turn.content for turn in second_history] == [
        "Tell me about The Arab Tent.",
        "response",
    ]
    assert all(
        turn.subjects == ["The Arab Tent"]
        for turn in second_history
    )


def test_empty_subject_list_is_stored_without_singular_subject_state():
    resolver = FakeResolver(subjects=[])
    engine = QueryEngine(
        subject_resolver=resolver,
        prompt_builder=FakePromptBuilder(),
        response_generator=FakeResponseGenerator("Hello."),
    )

    result = engine.generate_response(
        text="Hello",
        include_debug=True,
    )

    history = get_recent_conversation_history(
        conversation_id=result.conversation_id,
    )
    assert len(history) == 2
    assert history[0].subjects == []
    assert history[1].subjects == []
    assert history[0].current_subject is None
    assert history[0].current_subject_reference is None

    assert result.debug is not None
    assert result.debug.retrieval_used is False


def test_original_utterance_is_passed_to_prompt_builder():
    prompt_builder = FakePromptBuilder()
    response_generator = FakeResponseGenerator()
    engine = QueryEngine(
        subject_resolver=FakeResolver(
            subjects=["The Arab Tent"]
        ),
        prompt_builder=prompt_builder,
        response_generator=response_generator,
    )

    utterance = "Why does The Arab Tent look theatrical?"
    engine.generate_response(text=utterance)

    assert prompt_builder.calls[0][0] == utterance
    assert response_generator.calls[0][0] == (
        f"Prompt for: {utterance}"
    )
