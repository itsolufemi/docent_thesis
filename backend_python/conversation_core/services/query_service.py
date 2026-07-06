from collections.abc import Callable

from conversation_core.memory.conversation_store import (
    add_dialogue_turn,
    get_conversation,
    get_recent_conversation_history,
)
from conversation_core.schemas.context_schemas import QueryDebugInfo
from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.prompt_schemas import PromptProfile
from conversation_core.schemas.query_schemas import (
    QueryResult,
    ResolvedContext,
)
from conversation_core.services.llm_service import generate_llm_response
from conversation_core.services.prompt_service import build_prompt


SubjectResolver = Callable[
    [str | None, str],
    ResolvedContext,
]

PromptBuilder = Callable[
    [str, list[DialogueTurn], ResolvedContext],
    str,
]

ResponseGenerator = Callable[[str], str]


class QueryEngine:
    def __init__(
        self,
        subject_resolver: SubjectResolver,
        prompt_builder: PromptBuilder,
        response_generator: ResponseGenerator | None = None,
    ):
        self.subject_resolver = subject_resolver
        self.prompt_builder = prompt_builder
        self.response_generator = response_generator or generate_llm_response

    def generate_response(
        self,
        text: str,
        conversation_id: str | None = None,
        subject_reference: str | None = None,
        include_debug: bool = False,
    ) -> QueryResult:
        conversation_state = None
        dialogue_history: list[DialogueTurn] = []

        if conversation_id is not None:
            conversation_state = get_conversation(conversation_id)

            if conversation_state is not None:
                dialogue_history = get_recent_conversation_history(
                    conversation_id=conversation_id,
                )

                if subject_reference is None:
                    subject_reference = conversation_state.current_subject

        resolved_context = self.subject_resolver(
            subject_reference,
            text,
        )

        prompt = self.prompt_builder(
            text,
            dialogue_history,
            resolved_context,
        )

        response = self.response_generator(prompt)

        if conversation_state is not None:
            add_dialogue_turn(
                conversation_id=conversation_state.conversation_id,
                role="user",
                content=text,
            )

            add_dialogue_turn(
                conversation_id=conversation_state.conversation_id,
                role="assistant",
                content=response,
            )

        debug = None

        if include_debug:
            debug = QueryDebugInfo(
                conversation_found=conversation_state is not None,
                subject_reference=resolved_context.subject_reference,
                context_source=resolved_context.context_source,
                context_used=bool(
                    resolved_context.sources or resolved_context.prompt_payload
                ),
                dialogue_turns_used=len(dialogue_history),
                prompt=prompt,
                retrieval_used=resolved_context.context_source
                not in [
                    "no_context",
                    "no_external_context",
                    "subject_reference",
                    "subject_not_found",
                ],
                sources_count=len(resolved_context.sources),
                sources=resolved_context.sources,
                debug_payload=resolved_context.debug_payload,
            )

        return QueryResult(
            request=text,
            response=response,
            conversation_id=conversation_id,
            subject_reference=resolved_context.subject_reference,
            sources=resolved_context.sources,
            debug=debug,
        )


DEFAULT_CONVERSATION_PROFILE = PromptProfile(
    assistant_name="Assistant",
    user_name="User",
    assistant_role="You are a helpful conversational AI assistant.",
    behavioural_rules=[
        "Respond naturally.",
        "Use the recent dialogue to understand follow-up questions.",
        "If no external context is provided, do not pretend that you have one.",
    ],
)


def default_resolve_context(
    subject_reference: str | None,
    user_input: str,
) -> ResolvedContext:
    return ResolvedContext(
        context_source="no_external_context",
        subject_reference=subject_reference,
        sources=[],
        prompt_payload={},
        debug_payload={
            "note": "Default conversation engine used; no domain resolver configured.",
        },
    )


def default_build_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
) -> str:
    return build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
        profile=DEFAULT_CONVERSATION_PROFILE,
        context_sections=[],
    )


default_query_engine = QueryEngine(
    subject_resolver=default_resolve_context,
    prompt_builder=default_build_prompt,
)