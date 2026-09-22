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
from conversation_core.schemas.source_schemas import (  # noqa: E402
    QuerySource,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)


class FakeResolver:
    def __init__(
        self,
        *,
        subjects: list[str] | None = None,
        references: list[str] | None = None,
        context_source: str = "no_external_context",
    ) -> None:
        self.subjects = subjects or []
        self.references = references or []
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
            sources=[
                QuerySource(
                    source_type="retrieved_chunk",
                    reference=reference,
                )
                for reference in self.references
            ],
            prompt_payload={
                "subjects": list(self.subjects),
                "context_resolution": {
                    "is_relevant": True,
                    "route_type": "response_request",
                    "requires_retrieval": bool(
                        self.references
                    ),
                    "subjects": list(self.subjects),
                },
            },
            debug_payload={},
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


def test_generate_response_stores_one_complete_exchange():
    resolver = FakeResolver(
        subjects=[
            "The Arab Tent",
            "The Rising of the Sun",
        ],
        references=[
            "painting:581",
            "painting:119",
        ],
        context_source="subject_vector_retrieval",
    )
    engine = QueryEngine(
        subject_resolver=resolver,
        prompt_builder=FakePromptBuilder(),
        response_generator=FakeResponseGenerator(
            "They differ in subject and treatment."
        ),
    )

    result = engine.generate_response(
        text=(
            "Compare The Arab Tent and "
            "The Rising of the Sun."
        ),
        include_debug=True,
    )

    history = get_recent_conversation_history(
        conversation_id=result.conversation_id,
    )
    assert len(history) == 1

    exchange = history[0]
    assert exchange.previous_subject == []
    assert exchange.subject == [
        "The Arab Tent",
        "The Rising of the Sun",
    ]
    assert exchange.reference == [
        "painting:581",
        "painting:119",
    ]
    assert exchange.user == (
        "Compare The Arab Tent and "
        "The Rising of the Sun."
    )
    assert exchange.assistant == (
        "They differ in subject and treatment."
    )

    assert result.debug is not None
    assert result.debug.debug_payload["references"] == [
        "painting:581",
        "painting:119",
    ]


def test_follow_up_uses_prior_subject_as_previous_subject():
    resolver = FakeResolver(
        subjects=["The Arab Tent"],
        references=["painting:581"],
        context_source="subject_vector_retrieval",
    )
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

    history = get_recent_conversation_history(
        conversation_id=first.conversation_id,
    )
    assert len(history) == 2
    assert history[0].previous_subject == []
    assert history[0].subject == ["The Arab Tent"]
    assert history[1].previous_subject == [
        "The Arab Tent"
    ]
    assert history[1].subject == ["The Arab Tent"]

    second_resolver_history = resolver.calls[1][0]
    assert len(second_resolver_history) == 1
    assert second_resolver_history[0].user == (
        "Tell me about The Arab Tent."
    )
    assert second_resolver_history[0].assistant == "response"


def test_empty_subjects_and_references_are_valid():
    engine = QueryEngine(
        subject_resolver=FakeResolver(),
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
    assert len(history) == 1
    assert history[0].previous_subject == []
    assert history[0].subject == []
    assert history[0].reference == []
    assert history[0].user == "Hello"
    assert history[0].assistant == "Hello."

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
