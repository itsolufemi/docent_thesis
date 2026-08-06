from collections.abc import Callable
from threading import RLock
from time import perf_counter

from conversation_core.memory.conversation_store import (
    add_dialogue_turn,
    create_conversation,
    get_conversation,
    get_conversation_introduction,
    get_recent_conversation_history,
    set_conversation_introduction,
)
from conversation_core.schemas.context_schemas import QueryDebugInfo
from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.llm_stream_schemas import LLMStreamEvent
from conversation_core.schemas.prompt_schemas import PromptProfile
from conversation_core.schemas.query_schemas import QueryResult, ResolvedContext
from conversation_core.schemas.utterance_route_schemas import UtteranceRoute
from conversation_core.services.cancellation import CancellationToken
from conversation_core.services.introduction_service import IntroductionProvider
from conversation_core.services.llm_service import generate_llm_response
from conversation_core.services.plain_llm_stream_service import (
    stream_llm_response,
)
from conversation_core.services.prompt_service import build_prompt


NON_RETRIEVAL_CONTEXT_SOURCES = {
    "no_context",
    "no_external_context",
    "noise",
    "utterance_interruption",
    "utterance_call_to_action",
    "utterance_without_retrieval",
}


SubjectResolver = Callable[
    [list[DialogueTurn], str, UtteranceRoute | None],
    ResolvedContext,
]
PromptBuilder = Callable[
    [str, list[DialogueTurn], ResolvedContext],
    str,
]
ResponseGenerator = Callable[[str, str | None], str]
LLMStreamCallback = Callable[[LLMStreamEvent], None]
IntroductionResponseGenerator = Callable[[str], str]


def default_response_generator(
    prompt: str,
    conversation_id: str | None,
) -> str:
    return generate_llm_response(prompt)


def get_latest_subjects(
    dialogue_history: list[DialogueTurn],
) -> list[str]:
    for turn in reversed(dialogue_history):
        if turn.subjects:
            return list(turn.subjects)

    return []


def get_resolved_subjects(
    resolved_context: ResolvedContext,
) -> list[str]:
    raw_subjects = resolved_context.prompt_payload.get(
        "subjects",
        [],
    )

    if not isinstance(raw_subjects, list):
        return []

    subjects: list[str] = []
    seen: set[str] = set()

    for subject in raw_subjects:
        if not isinstance(subject, str):
            continue

        value = subject.strip()
        normalised = value.casefold()

        if not value or normalised in seen:
            continue

        seen.add(normalised)
        subjects.append(value)

    return subjects


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
        self.self_routing_enabled = self_routing_enabled
        self.introduction_provider = introduction_provider
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
                if self.introduction_provider is not None
                else None
            )

            if definition is None:
                return None, False

            try:
                response = self.introduction_response_generator(
                    definition.prompt
                ).strip()

                if response.lower().startswith(
                    ("error:", "ollama error:")
                ):
                    raise RuntimeError(response)
            except Exception:
                response = (
                    definition.fallback_text or ""
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

    def _prepare_conversation(
        self,
        conversation_id: str | None,
    ) -> tuple[object, str, bool, list[DialogueTurn]]:
        conversation_created = False
        conversation_state = (
            get_conversation(conversation_id)
            if conversation_id is not None
            else None
        )

        if conversation_state is None:
            conversation_state = create_conversation()
            conversation_id = conversation_state.conversation_id
            conversation_created = True

        dialogue_history = get_recent_conversation_history(
            conversation_id=conversation_id,
        )

        return (
            conversation_state,
            conversation_id,
            conversation_created,
            dialogue_history,
        )

    def generate_response(
        self,
        text: str,
        conversation_id: str | None = None,
        subject_reference: str | None = None,
        utterance_route: UtteranceRoute | None = None,
        include_debug: bool = False,
    ) -> QueryResult:
        request_started_at = perf_counter()
        (
            conversation_state,
            conversation_id,
            conversation_created,
            dialogue_history,
        ) = self._prepare_conversation(conversation_id)

        context_resolution_started_at = perf_counter()
        resolved_context = self.subject_resolver(
            dialogue_history,
            text,
            utterance_route,
        )
        context_resolution_seconds = (
            perf_counter() - context_resolution_started_at
        )

        subjects = get_resolved_subjects(resolved_context)
        prompt = self.prompt_builder(
            text,
            dialogue_history,
            resolved_context,
        )

        add_dialogue_turn(
            conversation_id=conversation_id,
            role="user",
            content=text,
            subjects=subjects,
        )

        response_generation_started_at = perf_counter()
        response = self.response_generator(
            prompt,
            conversation_id,
        )
        response_generation_seconds = (
            perf_counter() - response_generation_started_at
        )

        if response:
            add_dialogue_turn(
                conversation_id=conversation_id,
                role="assistant",
                content=response,
                subjects=subjects,
            )

        total_request_seconds = (
            perf_counter() - request_started_at
        )
        debug_payload = {
            **resolved_context.debug_payload,
            "conversation_created": conversation_created,
            "subjects": subjects,
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
            },
        }

        debug = None
        if include_debug:
            debug = QueryDebugInfo(
                conversation_found=True,
                subject_reference=None,
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
                debug_payload=debug_payload,
            )

        return QueryResult(
            request=text,
            response=response,
            conversation_id=conversation_id,
            subject_reference=None,
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

        preparation_started_at = perf_counter()
        (
            conversation_state,
            conversation_id,
            conversation_created,
            dialogue_history,
        ) = self._prepare_conversation(conversation_id)
        emit_timing(
            "conversation_preparation_seconds",
            perf_counter() - preparation_started_at,
        )

        context_resolution_started_at = perf_counter()
        resolved_context = self.subject_resolver(
            dialogue_history,
            text,
            utterance_route,
        )
        context_resolution_seconds = (
            perf_counter() - context_resolution_started_at
        )
        subjects = get_resolved_subjects(resolved_context)

        emit_timing(
            "context_resolution_seconds",
            context_resolution_seconds,
            context_source=resolved_context.context_source,
            source_count=len(resolved_context.sources),
            subjects=subjects,
        )

        context_resolution = (
            resolved_context.prompt_payload.get(
                "context_resolution"
            )
        )
        if (
            on_stream_event is not None
            and isinstance(context_resolution, dict)
        ):
            on_stream_event(
                LLMStreamEvent(
                    event_type="self_routing",
                    route_assessment=context_resolution,
                )
            )

        prompt_started_at = perf_counter()
        prompt = self.prompt_builder(
            text,
            dialogue_history,
            resolved_context,
        )
        emit_timing(
            "prompt_build_seconds",
            perf_counter() - prompt_started_at,
            prompt_characters=len(prompt),
            dialogue_turns=len(dialogue_history),
        )

        add_dialogue_turn(
            conversation_id=conversation_id,
            role="user",
            content=text,
            subjects=subjects,
        )

        response_generation_started_at = perf_counter()
        emit_timing(
            "pre_llm_total_seconds",
            response_generation_started_at - request_started_at,
        )

        response_parts: list[str] = []
        response_cancelled = (
            cancellation_token is not None
            and cancellation_token.is_cancelled
        )
        first_spoken_token_seconds: float | None = None

        if response_cancelled:
            if on_stream_event is not None:
                on_stream_event(
                    LLMStreamEvent(
                        event_type="response_cancelled",
                        done=True,
                    )
                )
        else:
            for stream_event in stream_llm_response(
                prompt=prompt,
                cancellation_token=cancellation_token,
            ):
                if stream_event.event_type == "content_delta":
                    if stream_event.text:
                        response_parts.append(stream_event.text)

                        if first_spoken_token_seconds is None:
                            first_spoken_token_seconds = (
                                perf_counter()
                                - response_generation_started_at
                            )
                            emit_timing(
                                "first_spoken_token_seconds",
                                first_spoken_token_seconds,
                            )

                elif stream_event.event_type == "response_cancelled":
                    response_cancelled = True

                if on_stream_event is not None:
                    on_stream_event(stream_event)

        response = "".join(response_parts).strip()
        response_cancelled = (
            response_cancelled
            or (
                cancellation_token is not None
                and cancellation_token.is_cancelled
            )
        )

        response_generation_seconds = (
            perf_counter() - response_generation_started_at
        )

        if not response_cancelled and response:
            add_dialogue_turn(
                conversation_id=conversation_id,
                role="assistant",
                content=response,
                subjects=subjects,
            )

        total_request_seconds = (
            perf_counter() - request_started_at
        )
        debug_payload = {
            **resolved_context.debug_payload,
            "conversation_created": conversation_created,
            "subjects": subjects,
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
                "first_spoken_token_seconds": (
                    round(first_spoken_token_seconds, 4)
                    if first_spoken_token_seconds is not None
                    else None
                ),
            },
        }

        debug = None
        if include_debug:
            debug = QueryDebugInfo(
                conversation_found=True,
                subject_reference=None,
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
                debug_payload=debug_payload,
            )

        return QueryResult(
            request=text,
            response=response,
            conversation_id=conversation_id,
            subject_reference=None,
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
    dialogue_history: list[DialogueTurn],
    user_input: str,
    utterance_route: UtteranceRoute | None = None,
) -> ResolvedContext:
    return ResolvedContext(
        context_source="no_external_context",
        subject_reference=None,
        sources=[],
        prompt_payload={"subjects": []},
        debug_payload={
            "note": (
                "Default conversation engine used; "
                "no domain resolver configured."
            ),
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
