from conversation_core.schemas.conversation_schemas import (
    DialogueTurn,
    ConversationBranch,
)
from conversation_core.schemas.query_schemas import ResolvedContext
from conversation_core.schemas.source_schemas import QuerySource
from conversation_core.schemas.utterance_route_schemas import (
    UtteranceRoute,
)
from conversation_core.services.query_service import (
    QueryEngine,
    self_routing_response_generator,
)
from conversation_core.services.utterance_router_service import route_utterance
from conversation_core.services.prompt_service import (
    format_conversation_branch_for_prompt,
)

from docent.config.docent_classifier_profile import docent_classifier_profile
from docent.services.artwork_service import get_painting_by_index
from docent.services.docent_prompt_service import docent_build_prompt
from docent.services.docent_retrieval_adapter import (
    get_docent_retrieval_documents,
)
from docent.services.source_service import (
    build_source_from_artwork,
    build_sources_from_retrieved_chunks,
    build_sources_from_retrieved_documents,
)
from extensions.retrieval.services.keyword_retrieval_service import (
    retrieve_documents_by_keyword,
)
from docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
)
from docent.services.introduction_service import build_docent_introduction

def docent_parse_subject_reference(
    subject_reference: str,
) -> int | None:
    if subject_reference.startswith("painting:"):
        raw_value = subject_reference.replace("painting:", "", 1)
    else:
        raw_value = subject_reference

    try:
        return int(raw_value)
    except ValueError:
        return None
    
def build_utterance_route_debug_payload(
    utterance_route,
    retrieval_skipped_by_utterance_route: bool,
) -> dict:
    return {
        "utterance_route_type": utterance_route.route_type,
        "utterance_is_relevant": utterance_route.is_relevant,
        "utterance_floor_intent": utterance_route.floor_intent,
        "utterance_route_confidence": utterance_route.confidence,
        "utterance_route_reason": utterance_route.reason,
        "utterance_requires_retrieval": (
            utterance_route.requires_retrieval
        ),
        "utterance_proposed_action": utterance_route.proposed_action,
        "utterance_candidate_subjects": utterance_route.candidate_subjects,
        "utterance_routing_seconds": utterance_route.routing_seconds,
        "retrieval_skipped_by_utterance_route": retrieval_skipped_by_utterance_route,
    }


def build_utterance_route_prompt_payload(
    utterance_route,
) -> dict:
    return {
        "route_type": utterance_route.route_type,
        "floor_intent": utterance_route.floor_intent,
        "requires_retrieval": utterance_route.requires_retrieval,
        "proposed_action": utterance_route.proposed_action,
        "candidate_subjects": utterance_route.candidate_subjects,
    }


def build_route_handled_context(
    utterance_route,
) -> ResolvedContext | None:
    if utterance_route.route_type == "noise":
        return ResolvedContext(
            context_source="noise",
            subject_reference=None,
            sources=[],
            prompt_payload={
                **build_utterance_route_prompt_payload(utterance_route),
                "route_handled_without_retrieval": True,
                "route_message": "The utterance was treated as noise.",
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": [],
            },
            debug_payload=build_utterance_route_debug_payload(
                utterance_route=utterance_route,
                retrieval_skipped_by_utterance_route=True,
            ),
        )

    if utterance_route.route_type == "interruption":
        return ResolvedContext(
            context_source="utterance_interruption",
            subject_reference=None,
            sources=[],
            prompt_payload={
                **build_utterance_route_prompt_payload(utterance_route),
                "route_handled_without_retrieval": True,
                "route_message": (
                    "The utterance was classified as an interruption. "
                    "No artwork retrieval was performed."
                ),
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": [],
            },
            debug_payload=build_utterance_route_debug_payload(
                utterance_route=utterance_route,
                retrieval_skipped_by_utterance_route=True,
            ),
        )

    if not utterance_route.requires_retrieval:
        route_message = (
            "The classifier determined that external domain retrieval "
            "is not required for this utterance."
        )

        if utterance_route.route_type == "call_to_action":
            route_message = (
                "The utterance requests a supported structural action. "
                "No domain retrieval is required. Use the proposed action "
                "and available conversation tools when appropriate."
            )

        return ResolvedContext(
            context_source="utterance_without_retrieval",
            subject_reference=None,
            sources=[],
            prompt_payload={
                **build_utterance_route_prompt_payload(utterance_route),
                "route_handled_without_retrieval": True,
                "route_message": route_message,
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": [],
            },
            debug_payload={
                **build_utterance_route_debug_payload(
                    utterance_route=utterance_route,
                    retrieval_skipped_by_utterance_route=True,
                ),
                "action_execution_available": (
                    utterance_route.route_type == "call_to_action"
                ),
            },
        )

    return None


def docent_resolve_context(
    subject_reference: str | None,
    user_input: str,
    utterance_route: UtteranceRoute | None = None,
) -> ResolvedContext:
    sources: list[QuerySource] = []
    active_utterance_route = (
        utterance_route
        or route_utterance(
            text=user_input,
            domain_profile=docent_classifier_profile,
        )
    )

    route_handled_context = build_route_handled_context(
        active_utterance_route
    )

    if route_handled_context is not None:
        return route_handled_context

    if subject_reference is not None:
        painting_index = docent_parse_subject_reference(subject_reference)

        if painting_index is not None:
            artwork = get_painting_by_index(painting_index)

            if artwork is not None:
                sources = [
                    build_source_from_artwork(
                        artwork=artwork,
                        source_type="artwork_context",
                    )
                ]

                return ResolvedContext(
                    context_source="subject_reference",
                    subject_reference=subject_reference,
                    sources=sources,
                    prompt_payload={
                        **build_utterance_route_prompt_payload(
                            active_utterance_route
                        ),
                        "artwork": artwork,
                        "retrieved_chunks": [],
                        "retrieved_documents": [],
                    },
                    debug_payload={
                        **build_utterance_route_debug_payload(
                            utterance_route=active_utterance_route,
                            retrieval_skipped_by_utterance_route=False,
                        ),
                        "painting_index": painting_index,
                        "artwork_found": True,
                    },
                )

            return ResolvedContext(
                context_source="subject_not_found",
                subject_reference=subject_reference,
                sources=[],
                prompt_payload={
                    **build_utterance_route_prompt_payload(
                        active_utterance_route
                    ),
                    "artwork": None,
                    "retrieved_chunks": [],
                    "retrieved_documents": [],
                },
                debug_payload={
                    **build_utterance_route_debug_payload(
                        utterance_route=active_utterance_route,
                        retrieval_skipped_by_utterance_route=False,
                    ),
                    "painting_index": painting_index,
                    "artwork_found": False,
                },
            )

    vector_retrieval_result = retrieve_docent_chunks_by_vector_similarity(
        query=user_input,
        limit=8,
        expand_parent_documents=True,
        use_hybrid_scoring=True,
        apply_confidence_gate=True,
        min_confidence_score=0.45,
    )
    retrieved_chunks = vector_retrieval_result.results

    if retrieved_chunks:
        return ResolvedContext(
            context_source="vector_retrieved_chunks",
            subject_reference=None,
            sources=build_sources_from_retrieved_chunks(retrieved_chunks),
            prompt_payload={
                **build_utterance_route_prompt_payload(
                    active_utterance_route
                ),
                "artwork": None,
                "retrieved_chunks": retrieved_chunks,
                "retrieved_documents": [],
            },
            debug_payload={
                **build_utterance_route_debug_payload(
                    utterance_route=active_utterance_route,
                    retrieval_skipped_by_utterance_route=False,
                ),
                "vector_retrieval_used": True,
                "parent_document_expansion_used": True,
                "hybrid_scoring_used": True,
                "confidence_gate_used": True,
                "min_confidence_score": 0.45,
                "retrieved_chunk_count": len(retrieved_chunks),
                "vector_retrieval_timings": (
                    vector_retrieval_result.timings.model_dump()
                ),
            }
        )

    documents = get_docent_retrieval_documents()

    retrieved_documents = retrieve_documents_by_keyword(
        query=user_input,
        documents=documents,
        limit=3,
    )

    if retrieved_documents:
        return ResolvedContext(
            context_source="retrieved_documents",
            subject_reference=None,
            sources=build_sources_from_retrieved_documents(retrieved_documents),
            prompt_payload={
                **build_utterance_route_prompt_payload(
                    active_utterance_route
                ),
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": retrieved_documents,
            },
            debug_payload={
                **build_utterance_route_debug_payload(
                    utterance_route=active_utterance_route,
                    retrieval_skipped_by_utterance_route=False,
                ),
                "document_retrieval_used": True,
                "retrieved_document_count": len(retrieved_documents),
                "vector_retrieval_timings": (
                    vector_retrieval_result.timings.model_dump()
                ),
            },
        )

    return ResolvedContext(
        context_source="no_external_context",
        subject_reference=None,
        sources=[],
        prompt_payload={
            **build_utterance_route_prompt_payload(
                active_utterance_route
            ),
            "artwork": None,
            "retrieved_chunks": [],
            "retrieved_documents": [],
        },
        debug_payload={
            **build_utterance_route_debug_payload(
                utterance_route=active_utterance_route,
                retrieval_skipped_by_utterance_route=False,
            ),
            "vector_retrieval_timings": (
                vector_retrieval_result.timings.model_dump()
            ),
        },
    )


def docent_build_prompt_from_context(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
    active_branch: ConversationBranch | None,
) -> str:
    branch_context = format_conversation_branch_for_prompt(
        active_branch
    )

    payload = resolved_context.prompt_payload
    route_type = payload.get("route_type", "response_request")
    floor_intent = payload.get("floor_intent", "none")
    proposed_action = payload.get("proposed_action")
    candidate_subjects = payload.get("candidate_subjects", [])

    classification_context = f"""
    UTTERANCE CLASSIFICATION

    Route type:
    {route_type}

    Floor intent:
    {floor_intent}

    Proposed structural action:
    {proposed_action or "None"}

    Candidate subjects:
    {candidate_subjects or "None"}
    """.strip()

    action_guidance = """
    The proposed action is advisory classifier output.

    Use a conversation-tree tool only when the user's request and the
    current conversation state justify it.

    For create_bounded_branch:
    - use retrieved artwork evidence to form an ordered remaining-subject list;
    - create the bounded branch with current_subjects empty;
    - do not mark the first subject current until the conversation actually
      begins discussing it.

    For close_bounded_branch:
    - close the active bounded branch only when the user clearly requests
      its termination or it has completed.
    """.strip()

    if payload.get("route_handled_without_retrieval"):
        return f"""
    You are Docent, a voice-led conversational guide.

    The user's utterance has already been classified by the conversation router.

    {classification_context}

    ACTIVE CONVERSATION BRANCH

    {branch_context}

    Routing note:
    {payload.get("route_message")}

    User utterance:
    {user_input}

    Respond briefly and naturally.

    The active branch represents the current overarching conversational activity.
    A digression does not automatically close a bounded branch.

    Use conversation-tree tools only when the branch state genuinely needs to change.

    {action_guidance}

    Do not invent artwork information.
    Do not use external context because none was retrieved.
    """.strip()

    user_input_with_branch_context = f"""
    {classification_context}

    ACTIVE CONVERSATION BRANCH

    {branch_context}

    CONVERSATION-TREE GUIDANCE

    The active branch represents the current overarching conversational activity.

    Do not close a bounded branch merely because the user asks a digressive or unrelated question.

    Keep a bounded branch active until:
    - its defined activity is complete; or
    - the user clearly asks to stop it.

    Use operational tools only when the conversation-tree state genuinely needs to change.

    {action_guidance}

    USER UTTERANCE

    {user_input}
    """.strip()

    return docent_build_prompt(
        user_input=user_input_with_branch_context,
        dialogue_history=dialogue_history,
        artwork=payload.get("artwork"),
        retrieved_documents=payload.get("retrieved_documents", []),
        retrieved_chunks=payload.get("retrieved_chunks", []),
    )


def build_candidate_subjects_from_chunks(
    retrieved_chunks,
) -> list[dict]:
    candidate_subjects: list[dict] = []
    seen_references: set[str] = set()

    for retrieved in retrieved_chunks:
        chunk = retrieved.chunk
        reference = (
            chunk.parent_document_id
        )

        if (
            not reference
            or reference in seen_references
        ):
            continue

        seen_references.add(reference)
        candidate_subjects.append(
            {
                "reference": reference,
                "label": (
                    chunk.title
                    or reference
                ),
                "score": float(
                    retrieved.score
                ),
            }
        )

    return candidate_subjects


def build_candidate_subjects_from_documents(
    retrieved_documents,
) -> list[dict]:
    candidate_subjects: list[dict] = []
    seen_references: set[str] = set()

    for retrieved in retrieved_documents:
        document = retrieved.document
        reference = (
            document.source_reference
            or document.document_id
        )

        if (
            not reference
            or reference in seen_references
        ):
            continue

        seen_references.add(reference)
        candidate_subjects.append(
            {
                "reference": reference,
                "label": (
                    document.title
                    or reference
                ),
                "score": float(
                    retrieved.score
                ),
            }
        )

    return candidate_subjects


def docent_resolve_self_routing_context(
    subject_reference: str | None,
    user_input: str,
    utterance_route: UtteranceRoute | None = None,
) -> ResolvedContext:
    if subject_reference is not None:
        painting_index = (
            docent_parse_subject_reference(
                subject_reference
            )
        )

        if painting_index is not None:
            artwork = get_painting_by_index(
                painting_index
            )

            if artwork is not None:
                return ResolvedContext(
                    context_source=(
                        "subject_reference"
                    ),
                    subject_reference=(
                        subject_reference
                    ),
                    sources=[
                        build_source_from_artwork(
                            artwork=artwork,
                            source_type=(
                                "artwork_context"
                            ),
                        )
                    ],
                    prompt_payload={
                        "artwork": artwork,
                        "retrieved_chunks": [],
                        "retrieved_documents": [],
                        "candidate_subjects": [
                            {
                                "reference": (
                                    subject_reference
                                ),
                                "label": (
                                    artwork.title
                                ),
                                "score": 1.0,
                            }
                        ],
                    },
                    debug_payload={
                        "self_routing_context_resolver": (
                            True
                        ),
                        "painting_index": (
                            painting_index
                        ),
                        "artwork_found": True,
                    },
                )

    vector_retrieval_result = (
        retrieve_docent_chunks_by_vector_similarity(
            query=user_input,
            limit=8,
            expand_parent_documents=True,
            use_hybrid_scoring=True,
            apply_confidence_gate=True,
            min_confidence_score=0.45,
        )
    )
    retrieved_chunks = (
        vector_retrieval_result.results
    )

    if retrieved_chunks:
        candidate_subjects = (
            build_candidate_subjects_from_chunks(
                retrieved_chunks
            )
        )

        return ResolvedContext(
            context_source=(
                "vector_retrieved_chunks"
            ),
            subject_reference=None,
            sources=(
                build_sources_from_retrieved_chunks(
                    retrieved_chunks
                )
            ),
            prompt_payload={
                "artwork": None,
                "retrieved_chunks": (
                    retrieved_chunks
                ),
                "retrieved_documents": [],
                "candidate_subjects": (
                    candidate_subjects
                ),
            },
            debug_payload={
                "self_routing_context_resolver": (
                    True
                ),
                "vector_retrieval_used": True,
                "parent_document_expansion_used": (
                    True
                ),
                "hybrid_scoring_used": True,
                "confidence_gate_used": True,
                "min_confidence_score": 0.45,
                "retrieved_chunk_count": len(
                    retrieved_chunks
                ),
                "candidate_subjects_count": len(
                    candidate_subjects
                ),
                "vector_retrieval_timings": (
                    vector_retrieval_result
                    .timings.model_dump()
                ),
            },
        )

    documents = get_docent_retrieval_documents()
    retrieved_documents = (
        retrieve_documents_by_keyword(
            query=user_input,
            documents=documents,
            limit=3,
        )
    )

    if retrieved_documents:
        candidate_subjects = (
            build_candidate_subjects_from_documents(
                retrieved_documents
            )
        )

        return ResolvedContext(
            context_source="retrieved_documents",
            subject_reference=None,
            sources=(
                build_sources_from_retrieved_documents(
                    retrieved_documents
                )
            ),
            prompt_payload={
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": (
                    retrieved_documents
                ),
                "candidate_subjects": (
                    candidate_subjects
                ),
            },
            debug_payload={
                "self_routing_context_resolver": (
                    True
                ),
                "document_retrieval_used": True,
                "retrieved_document_count": len(
                    retrieved_documents
                ),
                "candidate_subjects_count": len(
                    candidate_subjects
                ),
                "vector_retrieval_timings": (
                    vector_retrieval_result
                    .timings.model_dump()
                ),
            },
        )

    return ResolvedContext(
        context_source="no_external_context",
        subject_reference=None,
        sources=[],
        prompt_payload={
            "artwork": None,
            "retrieved_chunks": [],
            "retrieved_documents": [],
            "candidate_subjects": [],
        },
        debug_payload={
            "self_routing_context_resolver": (
                True
            ),
            "candidate_subjects_count": 0,
            "vector_retrieval_timings": (
                vector_retrieval_result
                .timings.model_dump()
            ),
        },
    )


SELF_ROUTING_OUTPUT_INSTRUCTIONS = """
SELF-ROUTING DECISION AND OUTPUT

Before composing the visitor-facing response, decide
the route internally using the fields described below.

If is_relevant is true:
- respond naturally to the visitor immediately;
- after the complete visitor-facing response, append
  exactly one internal routing footer.

If is_relevant is false:
- do not produce any visitor-facing response;
- output only the internal routing footer.

The routing footer must use exactly this format:

<route>{"route_type":"response_request","is_relevant":true,"candidate_subjects":["The Arab Tent"],"should_update_subject":true,"proposed_action":null,"confidence":0.98,"reason":"The user is asking about The Arab Tent."}</route>

The route block must contain valid JSON with exactly
the supplied fields.

The routing footer is internal metadata:
- never mention it in the visitor-facing response;
- never explain that routing occurred;
- never place visitor-facing text after </route>;
- emit the footer exactly once.

ROUTE RULES

- noise: the original utterance contains no
  meaningful conversational language. Set
  is_relevant=false and produce no visitor-facing
  response.
- response_request: the original utterance expects a
  spoken answer, including greetings, questions,
  explanations, comparisons, and ordinary follow-ups.
- call_to_action: the original utterance explicitly
  asks the system to begin, end, or change a
  structured activity.
- interruption: the original utterance stops,
  corrects, or redirects the assistant while it is
  speaking.

candidate_subjects must contain readable subject
names identified in the user's utterance, such as:

["The Arab Tent"]

or:

["The Swing", "The Arab Tent"]

Do not place internal references such as
"painting:581" in candidate_subjects.

Set candidate_subjects to an empty list when the
utterance has no identifiable subject.

Set should_update_subject only when the user's
primary conversational focus should change to one
of the identified candidate subjects.

proposed_action must describe an explicitly requested
structural action, or be null.

reason must briefly explain the routing decision and
subject decision.

Always classify the original USER UTTERANCE. If an
operational tool has returned a result, do not
reclassify the post-tool stage.
""".strip()


def docent_build_self_routing_prompt(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
    active_branch: ConversationBranch | None,
) -> str:
    payload = resolved_context.prompt_payload
    current_subject = (
        active_branch.current_subjects[0]
        if (
            active_branch is not None
            and active_branch.current_subjects
        )
        else None
    )
    current_subject_section = (
        "\n".join(
            [
                (
                    "Reference: "
                    f"{current_subject.reference or 'None'}"
                ),
                (
                    "Label: "
                    f"{current_subject.label}"
                ),
            ]
        )
        if current_subject is not None
        else "Reference: None\nLabel: None"
    )
    candidate_subjects = payload.get(
        "candidate_subjects",
        [],
    )
    candidate_lines = [
        (
            f"- {candidate['label']} "
            f"(retrieval score "
            f"{candidate['score']:.4f})"
        )
        for candidate in candidate_subjects
    ]
    candidate_section = (
        "\n".join(candidate_lines)
        or "None"
    )
    retrieval_available = bool(
        payload.get("artwork")
        or payload.get("retrieved_chunks")
        or payload.get("retrieved_documents")
    )
    branch_context = (
        format_conversation_branch_for_prompt(
            active_branch
        )
    )
    routed_user_input = f"""
{SELF_ROUTING_OUTPUT_INSTRUCTIONS}

RETRIEVAL AVAILABLE

{str(retrieval_available).lower()}

CURRENT SUBJECT

{current_subject_section}

RETRIEVED SUBJECT OPTIONS

{candidate_section}

ACTIVE CONVERSATION BRANCH

{branch_context}

The active branch is the current overarching
conversational activity. A digression does not close
a bounded branch. Use operational tools only when
conversation-tree state genuinely needs to change.

USER UTTERANCE

{user_input}
""".strip()

    return docent_build_prompt(
        user_input=routed_user_input,
        dialogue_history=dialogue_history,
        artwork=payload.get("artwork"),
        retrieved_documents=payload.get(
            "retrieved_documents",
            [],
        ),
        retrieved_chunks=payload.get(
            "retrieved_chunks",
            [],
        ),
    )


docent_query_engine = QueryEngine(
    subject_resolver=docent_resolve_context,
    prompt_builder=docent_build_prompt_from_context,
)

self_routing_docent_query_engine = QueryEngine(
    subject_resolver=(
        docent_resolve_self_routing_context
    ),
    prompt_builder=(
        docent_build_self_routing_prompt
    ),
    response_generator=(
        self_routing_response_generator
    ),
    self_routing_enabled=True,
    introduction_provider=(
        build_docent_introduction
    )
)
