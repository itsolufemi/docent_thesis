from collections.abc import Callable
from threading import RLock
from time import perf_counter

from conversation_core.memory.conversation_store import (
    add_dialogue_turn,
    create_conversation,
    get_active_branch,
    get_conversation,
    get_conversation_introduction,
    get_recent_conversation_history,
    set_conversation_introduction,
)
from conversation_core.schemas.context_schemas import QueryDebugInfo
from conversation_core.schemas.conversation_schemas import (
    DialogueTurn,
    ConversationBranch,
)
from conversation_core.schemas.llm_stream_schemas import (
    LLMStreamEvent,
)
from conversation_core.schemas.self_routing_schemas import (
    SelfRoutingAssessment,
)
from conversation_core.schemas.prompt_schemas import (
    PromptProfile,
    PromptSection,
)

from conversation_core.schemas.query_schemas import (
    QueryResult,
    ResolvedContext,
)
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.services.llm_service import (
    generate_llm_response,
    generate_tool_aware_llm_response,
    stream_tool_aware_llm_response,
)
from conversation_core.services.cancellation import (
    CancellationToken,
)
from conversation_core.services.prompt_service import (
    build_prompt,
    format_conversation_branch_for_prompt,
)
from conversation_core.services.self_routing_parser import (
    SelfRoutingStreamParser,
)
from conversation_core.services.introduction_service import (
    IntroductionProvider,
)


NON_RETRIEVAL_CONTEXT_SOURCES = {
    "no_context",
    "no_external_context",
    "subject_reference",
    "subject_not_found",
    "noise",
    "utterance_interruption",
    "utterance_call_to_action",
    "utterance_without_retrieval",
}


SubjectResolver = Callable[
    [str | None, str, UtteranceRoute | None],
    ResolvedContext,
]

PromptBuilder = Callable[
    [
        str,
        list[DialogueTurn],
        ResolvedContext,
        ConversationBranch | None,
    ],
    str,
]

ResponseGenerator = Callable[
    [str, str | None],
    str,
]

LLMStreamCallback = Callable[
    [LLMStreamEvent],
    None,
]

IntroductionResponseGenerator = Callable[
    [str],
    str,
]

def default_response_generator(
    prompt: str,
    conversation_id: str | None,
) -> str:
    if conversation_id is None:
        return generate_llm_response(prompt)

    return generate_tool_aware_llm_response(
        prompt=prompt,
        conversation_id=conversation_id,
    )


def self_routing_response_generator(
    prompt: str,
    conversation_id: str | None,
) -> str:
    if conversation_id is None:
        return generate_llm_response(prompt)

    response_parts: list[str] = []

    for event in stream_tool_aware_llm_response(
        prompt=prompt,
        conversation_id=conversation_id,
        buffer_for_tool_decision=False,
    ):
        if event.event_type == "content_delta":
            response_parts.append(event.text)

    return "".join(response_parts).strip()


def get_latest_subject_state(
    dialogue_history: list[DialogueTurn],
) -> tuple[
    str | None,
    str | None,
]:
    """
    Return the latest stored current subject and its reference.
    """
    for turn in reversed(dialogue_history):
        if turn.current_subject is not None:
            return (
                turn.current_subject,
                turn.current_subject_reference,
            )

    return None, None


def derive_retrieved_subject_state(
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
) -> tuple[
    str | None,
    str | None,
    str | None,
]:
    """
    Create the subject snapshot for the current exchange.

    Retrieval has already happened. This function merely stores the
    highest-ranked retrieved subject. When retrieval identifies no
    subject, the existing subject state is retained.
    """
    previous_subject, previous_reference = (
        get_latest_subject_state(
            dialogue_history
        )
    )

    candidate_subjects = (
        resolved_context.prompt_payload.get(
            "candidate_subjects",
            [],
        )
    )

    if candidate_subjects:
        primary_candidate = candidate_subjects[0]

        current_subject = primary_candidate.get(
            "label"
        )
        current_subject_reference = (
            primary_candidate.get(
                "reference"
            )
        )

        if (
            not isinstance(current_subject, str)
            or not current_subject.strip()
        ):
            return (
                previous_subject,
                previous_subject,
                previous_reference,
            )

        if not isinstance(
            current_subject_reference,
            str,
        ):
            current_subject_reference = None

        return (
            previous_subject,
            current_subject,
            current_subject_reference,
        )

    return (
        previous_subject,
        previous_subject,
        previous_reference,
    )


class QueryEngine:
    def __init__(
        self,
        subject_resolver: SubjectResolver,
        prompt_builder: PromptBuilder,
        response_generator: ResponseGenerator | None = None,
        self_routing_enabled: bool = False,
        introduction_provider: IntroductionProvider | None = None,
        introduction_response_generator: (
            IntroductionResponseGenerator | None
        ) = None,
    ):
        self.subject_resolver = subject_resolver
        self.prompt_builder = prompt_builder
        self.response_generator = (
            response_generator or default_response_generator
        )
        self.self_routing_enabled = (
            self_routing_enabled
        )
        self.introduction_provider = (
            introduction_provider
        )
        self.introduction_response_generator = (
            introduction_response_generator
            or generate_llm_response
        )
        self._introduction_lock = RLock()

    def ensure_introduction(
        self,
        *,
        conversation_id: str,
    ) -> tuple[str | None, bool]:
        """
        Return this conversation's introduction, generating it once.

        This is intentionally a direct, tool-free LLM request. It does
        not invoke context resolution, retrieval, classification, TRP,
        or the self-routing response parser.
        """
        with self._introduction_lock:
            existing = get_conversation_introduction(
                conversation_id
            )

            if existing is not None:
                return existing, False

            if get_conversation(conversation_id) is None:
                return None, False

            definition = (
                self.introduction_provider()
                if self.introduction_provider
                is not None
                else None
            )

            if definition is None:
                return None, False

            try:
                response = (
                    self.introduction_response_generator(
                        definition.prompt
                    )
                    .strip()
                )

                if response.lower().startswith(
                    ("error:", "ollama error:")
                ):
                    raise RuntimeError(response)
            except Exception:
                response = (
                    definition.fallback_text
                    or ""
                ).strip()

            if not response:
                return None, False

            if definition.store_as_dialogue_turn:
                add_dialogue_turn(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=response,
                )

            set_conversation_introduction(
                conversation_id,
                response,
            )

            return response, True

    def generate_introduction(
        self,
        *,
        conversation_id: str,
    ) -> str | None:
        introduction, _ = self.ensure_introduction(
            conversation_id=conversation_id
        )
        return introduction


    def generate_response(
        self,
        text: str,
        conversation_id: str | None = None,
        subject_reference: str | None = None,
        utterance_route: UtteranceRoute | None = None,
        include_debug: bool = False,
    ) -> QueryResult:
        """
        Process one user query.

        The method:
        1. Creates a conversation or loads its stored context.
        2. Resolves external/domain context.
        3. Builds the final prompt.
        4. Generates a response with conversation tools available.
        5. Saves the user and assistant turns.
        """
        request_started_at = perf_counter()

        conversation_created = False
        dialogue_history: list[DialogueTurn] = []
        active_branch: ConversationBranch | None = None

        conversation_state = None

        if conversation_id is not None:
            conversation_state = get_conversation(
                conversation_id
            )

        if conversation_state is None:
            conversation_state = create_conversation()
            conversation_id = conversation_state.conversation_id
            conversation_created = True

        if conversation_state is not None:
            dialogue_history = get_recent_conversation_history(
                conversation_id=conversation_id,
            )

            active_branch = get_active_branch(
                conversation_id=conversation_id,
            )

            _, latest_reference = (
                get_latest_subject_state(
                    dialogue_history
                )
            )

            if (
                subject_reference is None
                and latest_reference is not None
            ):
                subject_reference = latest_reference

        # Context resolution must happen for every request,
        # including requests without a stored conversation.

        context_resolution_started_at = perf_counter()

        resolved_context = self.subject_resolver(
            subject_reference,
            text,
            utterance_route,
        )

        context_resolution_seconds = (
            perf_counter() - context_resolution_started_at
        )

        (
            previous_subject,
            current_subject,
            current_subject_reference,
        ) = derive_retrieved_subject_state(
            dialogue_history=dialogue_history,
            resolved_context=resolved_context,
        )

        prompt = self.prompt_builder(
            text,
            dialogue_history,
            resolved_context,
            active_branch,
        )

        response_generation_started_at = perf_counter()

        response = self.response_generator(
            prompt,
            conversation_id,
        )

        response_generation_seconds = (
            perf_counter() - response_generation_started_at
        )
        self_routing_assessment: (
            SelfRoutingAssessment | None
        ) = None
        self_routing_validation_error: (
            str | None
        ) = None
        self_routing_consistent = True

        if self.self_routing_enabled:
            parser = SelfRoutingStreamParser()
            response = parser.consume(
                response
            ) + parser.finish()
            response = response.strip()
            self_routing_assessment = (
                parser.route
            )
            self_routing_validation_error = (
                parser.validation_error
            )

            if (
                self_routing_assessment is not None
                and not self_routing_assessment.is_relevant
                and response.strip()
            ):
                self_routing_consistent = False
                consistency_error = (
                    "The model produced visitor-facing text "
                    "while declaring is_relevant=false."
                )

                self_routing_validation_error = (
                    f"{self_routing_validation_error}; "
                    f"{consistency_error}"
                    if self_routing_validation_error
                    else consistency_error
                )

        # Store dialogue for newly created and existing conversations.
        if conversation_state is not None:
            add_dialogue_turn(
                conversation_id=conversation_state.conversation_id,
                role="user",
                content=text,
                previous_subject=previous_subject,
                current_subject=current_subject,
                current_subject_reference=(
                    current_subject_reference
                ),
            )

            if response:
                add_dialogue_turn(
                    conversation_id=(
                        conversation_state.conversation_id
                    ),
                    role="assistant",
                    content=response,
                    previous_subject=previous_subject,
                    current_subject=current_subject,
                    current_subject_reference=(
                        current_subject_reference
                    ),
                )
        
        total_request_seconds = (
            perf_counter() - request_started_at
        )

        timing_debug_payload = {
            **resolved_context.debug_payload,
            "conversation_created": conversation_created,
            "self_routing": (
                self_routing_assessment.model_dump(
                    mode="json"
                )
                if self_routing_assessment
                is not None
                else None
            ),
            "self_routing_valid": (
                self_routing_assessment
                is not None
            ),
            "self_routing_validation_error": (
                self_routing_validation_error
            ),
            "self_routing_consistent": (
                self_routing_consistent
            ),
            "timings": {
                "total_request_seconds": round(
                    total_request_seconds,
                    4,
                ),
                "context_resolution_seconds": round(
                    context_resolution_seconds,
                    4,
                ),
                "response_generation_seconds": round(
                    response_generation_seconds,
                    4,
                ),
                "self_routing_seconds": (
                    round(
                        response_generation_seconds,
                        4,
                    )
                    if self.self_routing_enabled
                    else None
                ),
            },
        }

        debug = None

        if include_debug:
            debug = QueryDebugInfo(
                conversation_found=conversation_state is not None,
                subject_reference=resolved_context.subject_reference,
                context_source=resolved_context.context_source,
                context_used=bool(
                    resolved_context.sources
                    or resolved_context.prompt_payload
                ),
                dialogue_turns_used=len(dialogue_history),
                prompt=prompt,
                retrieval_used=(
                    resolved_context.context_source
                    not in NON_RETRIEVAL_CONTEXT_SOURCES
                ),
                sources_count=len(resolved_context.sources),
                sources=resolved_context.sources,
                debug_payload=timing_debug_payload,
            )

        return QueryResult(
            request=text,
            response=response,
            conversation_id=conversation_id,
            subject_reference=resolved_context.subject_reference,
            sources=resolved_context.sources,
            debug=debug,
        )

    def generate_streaming_response(
        self,
        text: str,
        conversation_id: str | None = None,
        subject_reference: str | None = None,
        utterance_route: UtteranceRoute | None = None,
        include_debug: bool = False,
        on_stream_event: LLMStreamCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> QueryResult:
        request_started_at = perf_counter()

        def emit_timing(
            name: str,
            seconds: float,
            **payload,
        ) -> None:
            if on_stream_event is None:
                return

            on_stream_event(
                LLMStreamEvent(
                    event_type="timing",
                    timing_name=name,
                    timing_seconds=round(seconds, 4),
                    timing_payload=payload,
                )
            )

        conversation_preparation_started_at = perf_counter()
        conversation_created = False
        dialogue_history: list[DialogueTurn] = []
        active_branch: ConversationBranch | None = None
        conversation_state = None

        if conversation_id is not None:
            conversation_state = get_conversation(
                conversation_id
            )

        if conversation_state is None:
            conversation_state = create_conversation()
            conversation_id = conversation_state.conversation_id
            conversation_created = True

        if conversation_state is not None:
            dialogue_history = get_recent_conversation_history(
                conversation_id=conversation_id,
            )
            active_branch = get_active_branch(
                conversation_id=conversation_id,
            )

            _, latest_reference = (
                get_latest_subject_state(
                    dialogue_history
                )
            )

            if (
                subject_reference is None
                and latest_reference is not None
            ):
                subject_reference = latest_reference

        conversation_preparation_seconds = (
            perf_counter()
            - conversation_preparation_started_at
        )
        emit_timing(
            "conversation_preparation_seconds",
            conversation_preparation_seconds,
        )

        context_resolution_started_at = perf_counter()

        resolved_context = self.subject_resolver(
            subject_reference,
            text,
            utterance_route,
        )

        context_resolution_seconds = (
            perf_counter()
            - context_resolution_started_at
        )

        (
            previous_subject,
            current_subject,
            current_subject_reference,
        ) = derive_retrieved_subject_state(
            dialogue_history=dialogue_history,
            resolved_context=resolved_context,
        )

        emit_timing(
            "context_resolution_seconds",
            context_resolution_seconds,
            context_source=resolved_context.context_source,
            source_count=len(resolved_context.sources),
        )

        prompt_build_started_at = perf_counter()
        prompt = self.prompt_builder(
            text,
            dialogue_history,
            resolved_context,
            active_branch,
        )

        prompt_build_seconds = (
            perf_counter() - prompt_build_started_at
        )
        emit_timing(
            "prompt_build_seconds",
            prompt_build_seconds,
            prompt_characters=len(prompt),
            dialogue_turns=len(dialogue_history),
        )

        if conversation_state is not None:
            add_dialogue_turn(
                conversation_id=(
                    conversation_state.conversation_id
                ),
                role="user",
                content=text,
                previous_subject=previous_subject,
                current_subject=current_subject,
                current_subject_reference=(
                    current_subject_reference
                ),
            )

        response_generation_started_at = perf_counter()
        emit_timing(
            "pre_llm_total_seconds",
            response_generation_started_at - request_started_at,
        )
        self_routing_parser = (
            SelfRoutingStreamParser()
            if self.self_routing_enabled
            else None
        )
        self_routing_assessment: (
            SelfRoutingAssessment | None
        ) = None
        self_routing_footer_seconds: float | None = None
        first_spoken_token_seconds: (
            float | None
        ) = None

        def capture_completed_self_routing() -> None:
            nonlocal self_routing_assessment
            nonlocal self_routing_footer_seconds

            if (
                self_routing_parser is None
                or not self_routing_parser.route_just_completed
                or self_routing_footer_seconds is not None
            ):
                return

            self_routing_footer_seconds = (
                perf_counter()
                - response_generation_started_at
            )
            emit_timing(
                "self_routing_footer_seconds",
                self_routing_footer_seconds,
            )
            self_routing_assessment = (
                self_routing_parser.route
            )

            if on_stream_event is not None:
                on_stream_event(
                    LLMStreamEvent(
                        event_type="self_routing",
                        route_assessment=(
                            self_routing_assessment
                            .model_dump(mode="json")
                            if self_routing_assessment
                            is not None
                            else None
                        ),
                    )
                )

        response_cancelled = (
            cancellation_token is not None
            and cancellation_token.is_cancelled
        )

        if response_cancelled:
            response = ""

            if on_stream_event is not None:
                on_stream_event(
                    LLMStreamEvent(
                        event_type=(
                            "response_cancelled"
                        ),
                        done=True,
                    )
                )
        elif conversation_id is None:
            response = generate_llm_response(
                prompt
            )

            response_cancelled = (
                cancellation_token is not None
                and cancellation_token.is_cancelled
            )

            if (
                on_stream_event is not None
                and response_cancelled
            ):
                on_stream_event(
                    LLMStreamEvent(
                        event_type=(
                            "response_cancelled"
                        ),
                        done=True,
                    )
                )
            elif on_stream_event is not None:
                on_stream_event(
                    LLMStreamEvent(
                        event_type="response_started",
                    )
                )
                on_stream_event(
                    LLMStreamEvent(
                        event_type="content_delta",
                        text=response,
                    )
                )
                on_stream_event(
                    LLMStreamEvent(
                        event_type="response_complete",
                        text=response,
                        done=True,
                    )
                )
        else:
            response_parts: list[str] = []
            buffer_for_tool_decision = (
                utterance_route is not None
                and utterance_route.route_type
                == "call_to_action"
            )

            for stream_event in (
                stream_tool_aware_llm_response(
                    prompt=prompt,
                    conversation_id=conversation_id,
                    buffer_for_tool_decision=(
                        buffer_for_tool_decision
                    ),
                    cancellation_token=(
                        cancellation_token
                    ),
                )
            ):
                if response_cancelled:
                    continue

                if (
                    stream_event.event_type
                    == "content_delta"
                ):
                    spoken_delta = (
                        stream_event.text
                    )

                    if (
                        self_routing_parser
                        is not None
                    ):
                        spoken_delta = (
                            self_routing_parser
                            .consume(
                                stream_event.text
                            )
                        )

                    if spoken_delta:
                        response_parts.append(
                            spoken_delta
                        )

                        if (
                            first_spoken_token_seconds
                            is None
                        ):
                            first_spoken_token_seconds = (
                                perf_counter()
                                - response_generation_started_at
                            )
                            emit_timing(
                                "first_spoken_token_seconds",
                                first_spoken_token_seconds,
                            )

                        if on_stream_event is not None:
                            on_stream_event(
                                LLMStreamEvent(
                                    event_type=(
                                        "content_delta"
                                    ),
                                    text=spoken_delta,
                                )
                            )

                    capture_completed_self_routing()

                    continue

                if (
                    stream_event.event_type
                    == "response_complete"
                    and self_routing_parser
                    is not None
                ):
                    final_spoken_text = (
                        self_routing_parser.finish()
                    )

                    if final_spoken_text:
                        response_parts.append(
                            final_spoken_text
                        )

                        if (
                            first_spoken_token_seconds
                            is None
                        ):
                            first_spoken_token_seconds = (
                                perf_counter()
                                - response_generation_started_at
                            )
                            emit_timing(
                                "first_spoken_token_seconds",
                                first_spoken_token_seconds,
                            )

                        if on_stream_event is not None:
                            on_stream_event(
                                LLMStreamEvent(
                                    event_type=(
                                        "content_delta"
                                    ),
                                    text=final_spoken_text,
                                )
                            )

                    capture_completed_self_routing()

                    if on_stream_event is not None:
                        on_stream_event(
                            LLMStreamEvent(
                                event_type=(
                                    "response_complete"
                                ),
                                text="".join(
                                    response_parts
                                ).strip(),
                                done=True,
                            )
                        )
                    continue

                if (
                    stream_event.event_type
                    == "response_cancelled"
                ):
                    response_cancelled = True

                    if self_routing_parser is not None:
                        self_routing_parser.cancel()

                if on_stream_event is not None:
                    on_stream_event(
                        stream_event
                    )

            response = "".join(
                response_parts
            ).strip()

        response_cancelled = (
            response_cancelled
            or (
                cancellation_token is not None
                and cancellation_token.is_cancelled
            )
        )

        if (
            response_cancelled
            and self_routing_parser is not None
        ):
            self_routing_parser.cancel()

        response_generation_seconds = (
            perf_counter()
            - response_generation_started_at
        )

        self_routing_consistent = True

        if (
            self_routing_assessment is not None
            and not self_routing_assessment.is_relevant
            and response
        ):
            self_routing_consistent = False

        if conversation_state is not None:
            if (
                not response_cancelled
                and response
            ):
                add_dialogue_turn(
                    conversation_id=(
                        conversation_state
                        .conversation_id
                    ),
                    role="assistant",
                    content=response,
                    previous_subject=previous_subject,
                    current_subject=current_subject,
                    current_subject_reference=(
                        current_subject_reference
                    ),
                )

        total_request_seconds = (
            perf_counter() - request_started_at
        )

        timing_debug_payload = {
            **resolved_context.debug_payload,
            "conversation_created": conversation_created,
            "self_routing": (
                self_routing_assessment.model_dump(
                    mode="json"
                )
                if self_routing_assessment
                is not None
                else None
            ),
            "self_routing_valid": (
                self_routing_assessment
                is not None
            ),
            "self_routing_validation_error": (
                self_routing_parser
                .validation_error
                if self_routing_parser
                is not None
                else None
            ),
            "self_routing_consistent": (
                self_routing_consistent
            ),
            "timings": {
                "total_request_seconds": round(
                    total_request_seconds,
                    4,
                ),
                "context_resolution_seconds": round(
                    context_resolution_seconds,
                    4,
                ),
                "response_generation_seconds": round(
                    response_generation_seconds,
                    4,
                ),
                "self_routing_footer_seconds": (
                    round(
                        self_routing_footer_seconds,
                        4,
                    )
                    if self_routing_footer_seconds
                    is not None
                    else None
                ),
                # Temporary compatibility alias for existing benchmark
                # consumers. This now measures footer completion.
                "self_routing_seconds": (
                    round(
                        self_routing_footer_seconds,
                        4,
                    )
                    if self_routing_footer_seconds
                    is not None
                    else None
                ),
                "first_spoken_token_seconds": (
                    round(
                        first_spoken_token_seconds,
                        4,
                    )
                    if first_spoken_token_seconds
                    is not None
                    else None
                ),
            },
        }

        debug = None

        if include_debug:
            debug = QueryDebugInfo(
                conversation_found=(
                    conversation_state is not None
                ),
                subject_reference=(
                    resolved_context.subject_reference
                ),
                context_source=(
                    resolved_context.context_source
                ),
                context_used=bool(
                    resolved_context.sources
                    or resolved_context.prompt_payload
                ),
                dialogue_turns_used=len(
                    dialogue_history
                ),
                prompt=prompt,
                retrieval_used=(
                    resolved_context.context_source
                    not in NON_RETRIEVAL_CONTEXT_SOURCES
                ),
                sources_count=len(
                    resolved_context.sources
                ),
                sources=resolved_context.sources,
                debug_payload=timing_debug_payload,
            )

        return QueryResult(
            request=text,
            response=response,
            conversation_id=conversation_id,
            subject_reference=(
                resolved_context.subject_reference
            ),
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
    utterance_route: UtteranceRoute | None = None,
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
    active_branch: ConversationBranch | None,
) -> str:
    branch_context = format_conversation_branch_for_prompt(
        active_branch
    )

    return build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
        profile=DEFAULT_CONVERSATION_PROFILE,
        context_sections=[
            PromptSection(
                title="Active conversation branch",
                content=f"""
                    {branch_context}

                    Operational rules:
                    - A digression does not close an active bounded branch.
                    - Keep a bounded branch active until its activity is complete or the user clearly asks to stop.
                    - Use operational tools only when conversation-tree state actually needs to change.
                """.strip(),
            )
        ],
    )

default_query_engine = QueryEngine(
    subject_resolver=default_resolve_context,
    prompt_builder=default_build_prompt,
)
