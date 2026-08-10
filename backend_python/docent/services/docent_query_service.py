import json
from time import perf_counter

from conversation_core.schemas.context_resolution_schemas import (
    ContextResolutionAssessment,
)
from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.query_schemas import ResolvedContext
from conversation_core.services.llm_service import generate_llm_response
from conversation_core.services.prompt_service import (
    format_dialogue_history_for_prompt,
)
from conversation_core.services.query_service import QueryEngine
from docent.services.docent_prompt_service import docent_build_prompt
from docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
)
from docent.services.introduction_service import build_docent_introduction
from docent.services.source_service import (
    build_sources_from_retrieved_chunks,
)


CONTEXT_RESOLUTION_INSTRUCTIONS = """
You resolve conversational context for a museum guide before retrieval.

Use the current utterance and recent dialogue to return exactly one JSON object
with these fields:

- is_relevant: true when the utterance contains meaningful conversational input,
  including a backchannel; false only for noise or input that should be ignored.
- route_type: one of response_request, call_to_action, interruption,
  backchannel, or noise. Use backchannel for brief acknowledgements such as
  "yeah", "right", "mm-hm", "okay", "I see", or similar signals of continued
  attention. Use noise only for input that has no
  meaningful conversational content.
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
        "context_resolution_raw": raw_response,
        "context_resolution_validation_error": validation_error,
        "context_resolution_model_seconds": round(
            perf_counter() - started_at,
            4,
        ),
    }

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
            "subject_retrievals": subject_retrievals,
            "retrieved_chunk_count": len(retrieved_chunks),
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
Otherwise, answer the original visitor utterance naturally. Use the retrieved
evidence when available. The subject list is retrieval and dialogue metadata;
do not recite or explain it to the visitor.

ORIGINAL VISITOR UTTERANCE
{user_input}
""".strip()

    return docent_build_prompt(
        user_input=routing_guidance,
        dialogue_history=dialogue_history,
        artwork=payload.get("artwork"),
        retrieved_documents=payload.get("retrieved_documents", []),
        retrieved_chunks=payload.get("retrieved_chunks", []),
    )


context_resolved_docent_query_engine = QueryEngine(
    subject_resolver=docent_resolve_context,
    prompt_builder=docent_build_context_resolved_prompt,
    self_routing_enabled=False,
    introduction_provider=build_docent_introduction,
)
