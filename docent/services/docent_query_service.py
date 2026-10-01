import json
import logging
from collections.abc import Callable
from time import perf_counter

from conversation_core.memory.conversation_store import (
    get_recent_conversation_history,
)
from conversation_core.schemas.context_resolution_schemas import (
    ContextResolutionAssessment,
)
from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.llm_stream_schemas import LLMStreamEvent
from conversation_core.schemas.query_schemas import QueryResult, ResolvedContext
from conversation_core.schemas.utterance_route_schemas import UtteranceRoute
from conversation_core.services.cancellation import CancellationToken
from conversation_core.services.conversation_log_service import (
    append_telemetry_log,
)
from conversation_core.services.diagnostic_summary_service import (
    verbose_diagnostics_enabled,
)
from conversation_core.services.llm_service import generate_llm_response
from conversation_core.services.prompt_service import (
    format_dialogue_history_for_prompt,
)
from conversation_core.services.query_service import QueryEngine
from docent.services.docent_prompt_service import (
    build_docent_content_policy_debug,
    docent_build_prompt,
)
from docent.schemas.preference_schemas import (
    DocentPreferenceEvidence,
    DocentPreferenceState,
)
from docent.services.docent_preference_analyser import (
    analyse_docent_preferences,
)
from docent.services.docent_diagnostic_service import (
    build_preference_telemetry_summary,
    build_retrieval_debug_summary,
)
from docent.services.docent_discovery_store import (
    mark_prepared_discovery_surfaced_from_response,
)
from docent.services.docent_preference_service import (
    update_docent_preferences,
    use_docent_preference_state,
)
from docent.services.docent_preference_store import (
    DocentPreferenceStore,
    docent_preference_store,
)
from docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
)
from docent.services.introduction_service import build_docent_introduction
from docent.services.source_service import (
    build_sources_from_retrieved_chunks,
)
from docent.tools import docent_tool_registry


logger = logging.getLogger(__name__)
PreferenceAnalyser = Callable[
    [list[DialogueTurn], str, DocentPreferenceState],
    tuple[DocentPreferenceEvidence, dict],
]
LLMStreamCallback = Callable[[LLMStreamEvent], None]


CONTEXT_RESOLUTION_INSTRUCTIONS = """
You resolve conversational context for a museum guide before retrieval.

Use the current utterance and recent dialogue to return exactly one JSON object
with these fields:

- is_relevant: true when the utterance contains meaningful conversational input,
  including a backchannel; false only for noise or input that should be ignored.
- route_type: one of response_request, call_to_action, interruption,
  backchannel, or potential_noise.

  response_request:
  Any meaningful conversational contribution that merits a verbal response
  from the assistant. This includes questions, greetings, answers to the
  assistant's questions, confirmations, corrections, requests for
  explanation, changes of subject, and acknowledgements that function as a
  response or invite the conversation to continue.

  call_to_action:
  Use only when the user is asking the system to perform an available
  executable action that would be handled through a tool or application
  capability, rather than merely asking the assistant to say something.
  Do not use call_to_action simply because the user uses an imperative.
  A request such as "tell me about The Swing" is a response_request if it
  only requires a verbal answer. A request that should trigger an available
  tool or application action is a call_to_action.

  interruption:
  Use when the user is deliberately taking the floor from an assistant that
  is currently speaking in order to stop, correct, redirect, or replace the
  assistant's current response. Do not classify an ordinary new turn as an
  interruption merely because it is short or abrupt.

  backchannel:
  A brief acknowledgement that supports the assistant continuing, such as
  "mm-hm", "right", "okay", or "I see", when it does not introduce a new
  question, correction, request, answer, or change in conversational
  direction.

  potential_noise:
  Use only when the input contains no meaningful conversational contribution
  and should be ignored. This includes non-linguistic sounds, accidental
  transcription, meaningless fragments, or speech that does not carry a
  discernible conversational function. Do not classify meaningful
  acknowledgements as noise, and do not classify noise as backchannel.

Classify by conversational function in the current dialogue, not by the
surface words alone. Short utterances such as "yeah", "right", "okay", or
"I see" may be backchannels, response requests, or occasionally noise
depending on what they are doing in context.
- requires_retrieval: true only when external artwork information is needed to
  answer the current utterance.
- subjects: readable names of every subject for which information should be
  retrieved or retained as conversational context. Use an empty list when no
  subject is identifiable.

Resolve references from the dialogue. For example, if the current utterance is
"Who painted it?" and the recent dialogue concerns The Arab Tent, include
"The Arab Tent" in subjects.

For comparisons, include every compared subject. Do not choose a primary
subject. Do not add references, identifiers, confidence, reasons, explanations,
or any fields other than the four listed above.

Return JSON only. Do not use markdown fences.
""".strip()


def _clean_subjects(subjects: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for subject in subjects:
        if not isinstance(subject, str):
            continue

        value = subject.strip()
        normalised = value.casefold()

        if not value or normalised in seen:
            continue

        seen.add(normalised)
        cleaned.append(value)

    return cleaned


def _extract_json_object(text: str) -> str:
    stripped = text.strip()

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end < start:
        raise ValueError("Context resolver did not return a JSON object.")

    return stripped[start:end + 1]


def resolve_context_assessment(
    dialogue_history: list[DialogueTurn],
    user_input: str,
) -> tuple[ContextResolutionAssessment, dict]:
    started_at = perf_counter()
    formatted_history = format_dialogue_history_for_prompt(
        dialogue_history=dialogue_history,
        user_label="Visitor",
        assistant_label="Docent",
    )

    prompt = f"""
{CONTEXT_RESOLUTION_INSTRUCTIONS}

RECENT DIALOGUE
{formatted_history}

CURRENT UTTERANCE
{user_input}

JSON:
""".strip()

    raw_response = generate_llm_response(
        prompt=prompt,
        options={
            "temperature": 0,
        },
        think=False,
    )

    validation_error: str | None = None

    try:
        assessment = ContextResolutionAssessment.model_validate(
            json.loads(_extract_json_object(raw_response))
        )
        assessment.subjects = _clean_subjects(assessment.subjects)
    except Exception as error:
        validation_error = str(error)
        assessment = ContextResolutionAssessment(
            is_relevant=True,
            route_type="response_request",
            requires_retrieval=True,
            subjects=[user_input.strip()] if user_input.strip() else [],
        )

    debug = {
        "context_resolution": assessment.model_dump(mode="json"),
        "context_resolution_model_seconds": round(
            perf_counter() - started_at,
            4,
        ),
    }
    if validation_error is not None:
        debug["context_resolution_raw"] = raw_response
        debug["context_resolution_validation_error"] = validation_error

    if validation_error is None and verbose_diagnostics_enabled():
        debug["context_resolution_raw"] = raw_response

    return assessment, debug


def _retrieve_subjects(
    subjects: list[str],
    *,
    per_subject_limit: int = 4,
    merged_limit: int = 10,
) -> tuple[list, list[dict]]:
    merged_results = []
    seen_chunk_ids: set[str] = set()
    subject_retrievals: list[dict] = []

    for subject in subjects:
        retrieval_result = retrieve_docent_chunks_by_vector_similarity(
            query=subject,
            limit=per_subject_limit,
            expand_parent_documents=True,
            use_hybrid_scoring=True,
            apply_confidence_gate=True,
            min_confidence_score=0.45,
        )

        accepted_references: list[str] = []
        accepted_chunk_ids: list[str] = []

        for retrieved in retrieval_result.results:
            chunk = retrieved.chunk
            chunk_id = chunk.chunk_id

            if chunk_id in seen_chunk_ids:
                continue

            seen_chunk_ids.add(chunk_id)
            merged_results.append(retrieved)
            accepted_chunk_ids.append(chunk_id)

            reference = chunk.source_reference or chunk.parent_document_id
            if reference and reference not in accepted_references:
                accepted_references.append(reference)

        subject_retrievals.append(
            {
                "subject": subject,
                "result_count": len(retrieval_result.results),
                "accepted_chunk_ids": accepted_chunk_ids,
                "references": accepted_references,
                "timings": retrieval_result.timings.model_dump(),
            }
        )

    merged_results.sort(
        key=lambda retrieved: float(retrieved.score),
        reverse=True,
    )

    return merged_results[:merged_limit], subject_retrievals


def docent_resolve_context(
    dialogue_history: list[DialogueTurn],
    user_input: str,
    utterance_route=None,
) -> ResolvedContext:
    assessment, resolution_debug = resolve_context_assessment(
        dialogue_history=dialogue_history,
        user_input=user_input,
    )

    retrieved_chunks = []
    subject_retrievals: list[dict] = []

    if assessment.requires_retrieval and assessment.subjects:
        retrieved_chunks, subject_retrievals = _retrieve_subjects(
            assessment.subjects
        )

    context_source = (
        "subject_vector_retrieval"
        if retrieved_chunks
        else "no_external_context"
    )

    return ResolvedContext(
        context_source=context_source,
        subject_reference=None,
        sources=build_sources_from_retrieved_chunks(retrieved_chunks),
        prompt_payload={
            "context_resolution": assessment.model_dump(mode="json"),
            "subjects": assessment.subjects,
            "retrieved_chunks": retrieved_chunks,
            "retrieved_documents": [],
            "artwork": None,
        },
        debug_payload={
            **resolution_debug,
            "retrieval": build_retrieval_debug_summary(
                subjects=assessment.subjects,
                retrieved_chunks=retrieved_chunks,
                subject_retrievals=subject_retrievals,
            ),
        },
    )


def docent_build_context_resolved_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
) -> str:
    payload = resolved_context.prompt_payload
    assessment = payload.get("context_resolution", {})

    routing_guidance = f"""
CONTEXT RESOLUTION
is_relevant: {assessment.get('is_relevant', True)}
route_type: {assessment.get('route_type', 'response_request')}
requires_retrieval: {assessment.get('requires_retrieval', False)}
subjects: {assessment.get('subjects', [])}

If is_relevant is false, produce no visitor-facing response.
Otherwise, answer the final visitor turn in Recent dialogue naturally. Use the
retrieved evidence when available. The subject list is retrieval and dialogue
metadata; do not recite or explain it to the visitor.
""".strip()

    return docent_build_prompt(
        user_input=routing_guidance,
        dialogue_history=dialogue_history,
        artwork=payload.get("artwork"),
        retrieved_documents=payload.get("retrieved_documents", []),
        retrieved_chunks=payload.get("retrieved_chunks", []),
        response_guidance=routing_guidance,
    )


def docent_build_direct_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
) -> str:
    del resolved_context

    return docent_build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
    )


class DocentPreferenceQueryService:
    """Add Docent session preferences around an unchanged query engine."""

    def __init__(
        self,
        query_engine: QueryEngine,
        *,
        analyser: PreferenceAnalyser = analyse_docent_preferences,
        preference_store: DocentPreferenceStore = docent_preference_store,
    ) -> None:
        self.query_engine = query_engine
        self.analyser = analyser
        self.preference_store = preference_store

    def __getattr__(self, name: str):
        return getattr(self.query_engine, name)

    @staticmethod
    def _record_discovery_outcome(
        result: QueryResult,
        request_id: str | None,
    ) -> None:
        conversation_id = result.conversation_id
        if conversation_id is None or not any(
            source.source_type == "discovery_evidence"
            for source in result.sources
        ):
            return

        state = mark_prepared_discovery_surfaced_from_response(
            conversation_id,
            result.response,
        )
        if state is None:
            return

        continuation = result.response
        if (
            state.source_response_text
            and result.response.startswith(state.source_response_text)
        ):
            continuation = result.response[len(state.source_response_text):]

        append_telemetry_log(
            conversation_id=conversation_id,
            request_id=request_id,
            event_type="docent_discovery_outcome",
            payload={
                "query": state.query,
                "discovery_trigger_phase": (
                    state.discovery_trigger_phase
                ),
                "prepared_reused": state.prepared_reused,
                "prepared_candidates": {
                    "current_artwork": len(
                        state.current_artwork_candidates
                    ),
                    "collection": len(
                        state.collection_candidates
                    ),
                },
                "continuation_emitted": bool(continuation.strip()),
                "surfaced_reference": state.surfaced_reference,
            },
        )

    @staticmethod
    def _history_before_turn(
        conversation_id: str | None,
        override: list[DialogueTurn] | None = None,
    ) -> list[DialogueTurn]:
        history = (
            override
            if override is not None
            else (
                get_recent_conversation_history(conversation_id)
                if conversation_id is not None
                else []
            )
        )
        return [turn.model_copy(deep=True) for turn in history]

    def _analyse_after_response(
        self,
        *,
        text: str,
        conversation_id: str | None,
        request_id: str | None,
        dialogue_history: list[DialogueTurn],
        preference_snapshot: DocentPreferenceState,
    ) -> None:
        if conversation_id is None:
            return

        try:
            evidence, analysis_debug = self.analyser(
                dialogue_history,
                text,
                preference_snapshot,
            )
            before, after = update_docent_preferences(
                conversation_id,
                evidence,
                store=self.preference_store,
            )
            content_policy = build_docent_content_policy_debug(
                preference_snapshot
            )
            payload = build_preference_telemetry_summary(
                before=before,
                evidence=evidence,
                after=after,
                content_policy=content_policy,
                analysis=analysis_debug,
            )
            append_telemetry_log(
                conversation_id=conversation_id,
                request_id=request_id,
                event_type="docent_preference_update",
                payload=payload,
            )
            logger.info(
                "Updated Docent session preferences for conversation %s: %s",
                conversation_id,
                payload,
            )
        except Exception as error:
            logger.exception(
                "Docent preference analysis failed for conversation %s",
                conversation_id,
            )
            append_telemetry_log(
                conversation_id=conversation_id,
                request_id=request_id,
                event_type="docent_preference_analysis_failed",
                payload={"error": str(error)},
            )

    def generate_response(
        self,
        text: str,
        conversation_id: str | None = None,
        request_id: str | None = None,
        subject_reference: str | None = None,
        utterance_route: UtteranceRoute | None = None,
        include_debug: bool = False,
    ) -> QueryResult:
        preference_snapshot = self.preference_store.get(conversation_id)
        dialogue_history = self._history_before_turn(conversation_id)

        with use_docent_preference_state(preference_snapshot):
            result = self.query_engine.generate_response(
                text=text,
                conversation_id=conversation_id,
                request_id=request_id,
                subject_reference=subject_reference,
                utterance_route=utterance_route,
                include_debug=include_debug,
            )

        self._record_discovery_outcome(result, request_id)
        self._analyse_after_response(
            text=text,
            conversation_id=result.conversation_id,
            request_id=request_id,
            dialogue_history=dialogue_history,
            preference_snapshot=preference_snapshot,
        )
        return result

    def generate_streaming_response(
        self,
        text: str,
        conversation_id: str | None = None,
        request_id: str | None = None,
        dialogue_history_override: list[DialogueTurn] | None = None,
        interrupted_request_id: str | None = None,
        interrupted_assistant_text: str | None = None,
        subject_reference: str | None = None,
        utterance_route: UtteranceRoute | None = None,
        include_debug: bool = False,
        on_stream_event: LLMStreamCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> QueryResult:
        preference_snapshot = self.preference_store.get(conversation_id)
        dialogue_history = self._history_before_turn(
            conversation_id,
            dialogue_history_override,
        )

        with use_docent_preference_state(preference_snapshot):
            result = self.query_engine.generate_streaming_response(
                text=text,
                conversation_id=conversation_id,
                request_id=request_id,
                dialogue_history_override=dialogue_history_override,
                interrupted_request_id=interrupted_request_id,
                interrupted_assistant_text=interrupted_assistant_text,
                subject_reference=subject_reference,
                utterance_route=utterance_route,
                include_debug=include_debug,
                on_stream_event=on_stream_event,
                cancellation_token=cancellation_token,
            )

        self._record_discovery_outcome(result, request_id)
        self._analyse_after_response(
            text=text,
            conversation_id=result.conversation_id,
            request_id=request_id,
            dialogue_history=dialogue_history,
            preference_snapshot=preference_snapshot,
        )
        return result


context_resolved_docent_query_engine = QueryEngine(
    subject_resolver=docent_resolve_context,
    prompt_builder=docent_build_context_resolved_prompt,
    self_routing_enabled=False,
    introduction_provider=build_docent_introduction,
)


direct_docent_core_query_engine = QueryEngine(
    subject_resolver=None,
    prompt_builder=docent_build_direct_prompt,
    direct_routing_enabled=True,
    tool_registry=docent_tool_registry,
    introduction_provider=build_docent_introduction,
)


direct_docent_query_engine = DocentPreferenceQueryService(
    direct_docent_core_query_engine
)
