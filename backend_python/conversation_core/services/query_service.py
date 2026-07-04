from collections.abc import Callable

from backend_python.conversation_core.schemas.query_schemas import (
    QueryResult,
    ResolvedContext,
)

from backend_python.conversation_core.memory.conversation_store import (
    add_conversation_turn,
    get_conversation,
    get_recent_conversation_history,
)
from backend_python.conversation_core.schemas.conversation_schemas import (
    DialogueTurn,
)
from backend_python.conversation_core.schemas.source_schemas import QuerySource

from backend_python.conversation_core.services.llm_service import generate_llm_response



SubjectResolver = Callable[
    [str | None, str],
    ResolvedContext
]

PromptBuilder = Callable[
    [str, list[DialogueTurn], ResolvedContext],
    str
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
            add_conversation_turn(
                conversation_id=conversation_state.conversation_id,
                role="user",
                content=text,
            )

            add_conversation_turn(
                conversation_id=conversation_state.conversation_id,
                role="assistant",
                content=response,
            )

        debug = None

        if include_debug:
            debug = {
                "conversation_found": conversation_state is not None,
                "dialogue_turns_used": len(dialogue_history),
                "subject_reference": resolved_context.subject_reference,
                "context_source": resolved_context.context_source,
                "sources_count": len(resolved_context.sources),
                "prompt": prompt,
                "resolver_debug": resolved_context.debug_payload,
            }

        return QueryResult(
            request=text,
            response=response,
            conversation_id=conversation_id,
            subject_reference=resolved_context.subject_reference,
            sources=resolved_context.sources,
            debug=debug,
        )
