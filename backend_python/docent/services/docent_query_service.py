from backend_python.conversation_core.services.query_service import (
    QueryEngine,
    ResolvedContext,
)
from backend_python.conversation_core.services.source_service import (
    build_source_from_artwork,
    build_sources_from_retrieved_artworks,
    build_sources_from_retrieved_evidence_chunks,
)
from backend_python.docent.services.artwork_service import (
    get_painting_by_index,
)
from backend_python.retrieval.services.keyword_retrieval_service import (
    retrieve_artworks_for_query,
)
from backend_python.retrieval.services.rag_service import (
    retrieve_evidence_chunks_for_query,
)
from backend_python.conversation_core.services.prompt_service import (
    build_prompt,
)


def parse_painting_reference(
    subject_reference: str,
) -> int | None:
    if subject_reference.startswith("painting:"):
        raw_id = subject_reference.replace("painting:", "", 1)
    else:
        raw_id = subject_reference

    try:
        return int(raw_id)
    except ValueError:
        return None


def resolve_docent_subject(
    subject_reference: str | None,
    text: str,
) -> ResolvedConversationContext:
    if subject_reference is not None:
        painting_index = parse_painting_reference(subject_reference)

        if painting_index is not None:
            artwork = get_painting_by_index(painting_index)

            if artwork is not None:
                return ResolvedConversationContext(
                    context_source="subject_reference",
                    subject_reference=subject_reference,
                    prompt_context="",
                    sources=[
                        build_source_from_artwork(
                            artwork=artwork,
                            source_type="artwork_context",
                        )
                    ],
                    debug_payload={
                        "painting_index": painting_index,
                        "artwork_found": True,
                    },
                )

            return ResolvedConversationContext(
                context_source="subject_not_found",
                subject_reference=subject_reference,
                debug_payload={
                    "painting_index": painting_index,
                    "artwork_found": False,
                },
            )

    rag_results = retrieve_evidence_chunks_for_query(
        query=text,
        limit=5,
    )

    if rag_results:
        return ResolvedConversationContext(
            context_source="rag_evidence_chunks",
            subject_reference=None,
            sources=build_sources_from_retrieved_evidence_chunks(
                rag_results
            ),
            debug_payload={
                "rag_used": True,
                "rag_results": [
                    result.model_dump()
                    for result in rag_results
                ],
            },
        )

    retrieved_artworks = retrieve_artworks_for_query(
        query=text,
        limit=3,
    )

    if retrieved_artworks:
        return ResolvedConversationContext(
            context_source="keyword_retrieval_results",
            subject_reference=None,
            sources=build_sources_from_retrieved_artworks(
                retrieved_artworks
            ),
            debug_payload={
                "keyword_retrieval_used": True,
                "retrieval_results": [
                    result.model_dump()
                    for result in retrieved_artworks
                ],
            },
        )

    return ResolvedConversationContext(
        context_source="no_external_context",
        subject_reference=None,
        sources=[],
        debug_payload={},
    )