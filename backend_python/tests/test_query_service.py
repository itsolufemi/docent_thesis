from conversation_core.services.query_service import QueryEngine


class FakeResolver:
    def __call__(
        self,
        subject_reference,
        user_input,
        utterance_route=None,
    ):
        return type(
            "ResolvedContext",
            (),
            {
                "subject_reference": subject_reference,
                "context_source": "no_external_context",
                "sources": [],
                "prompt_payload": {},
                "debug_payload": {},
            },
        )()


class FakePromptBuilder:
    def __call__(self, user_input, dialogue_history, resolved_context, active_branch):
        return "prompt"


class FakeResponseGenerator:
    def __call__(self, prompt, conversation_id):
        return "response"


def test_generate_response_without_conversation_and_without_subject_reference_uses_defaults():
    engine = QueryEngine(
        subject_resolver=FakeResolver(),
        prompt_builder=FakePromptBuilder(),
        response_generator=FakeResponseGenerator(),
    )

    result = engine.generate_response(text="hello")

    assert result.response == "response"
    assert result.subject_reference is None
