from backend_python.conversation_core.schemas.conversation_schemas import DialogueTurn
from backend_python.conversation_core.schemas.query_schemas import ResolvedContext
from backend_python.conversation_core.services.query_service import QueryEngine
from backend_python.conversation_core.schemas.source_schemas import QuerySource

from backend_python.docent.services.artwork_service import get_painting_by_index
from backend_python.docent.services.docent_prompt_service import docent_build_prompt
from backend_python.extensions.retrieval.services.rag_service import retrieve_evidence_chunks_for_query
from backend_python.extensions.retrieval.services.keyword_retrieval_service import retrieve_artworks_for_query
from backend_python.docent.services.source_service import (
    build_source_from_artwork,
    build_sources_from_retrieved_artworks,
    build_sources_from_retrieved_evidence_chunks,
)

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

def docent_resolve_context(
    subject_reference: str | None,
    user_input: str,
) -> ResolvedContext:
    artwork = None
    rag_results = []
    retrieved_artworks = []
    sources: list[QuerySource] = []

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
                        "artwork": artwork,
                        "rag_results": [],
                        "retrieved_artworks": [],
                    },
                    debug_payload={
                        "painting_index": painting_index,
                        "artwork_found": True,
                    },
                )

            return ResolvedContext(
                context_source="subject_not_found",
                subject_reference=subject_reference,
                sources=[],
                prompt_payload={},
                debug_payload={
                    "painting_index": painting_index,
                    "artwork_found": False,
                },
            ) 
    
    rag_results = retrieve_evidence_chunks_for_query(
        query=user_input,
        limit=5,
        )

    if rag_results:
        return ResolvedContext(
            context_source="rag_evidence_chunks",
            subject_reference=None,
            sources=build_sources_from_retrieved_evidence_chunks(rag_results),
            prompt_payload={
                "artwork": None,
                "rag_results": rag_results,
                "retrieved_artworks": [],
            },
            debug_payload={
                "rag_used": True,
                "rag_result_count": len(rag_results),
            },
        )

    retrieved_artworks = retrieve_artworks_for_query(
        query=user_input,
        limit=3,
    )

    if retrieved_artworks:
        return ResolvedContext(
            context_source="keyword_retrieval_results",
            subject_reference=None,
            sources=build_sources_from_retrieved_artworks(retrieved_artworks),
            prompt_payload={
                "artwork": None,
                "rag_results": [],
                "retrieved_artworks": retrieved_artworks,
            },
            debug_payload={
                "keyword_retrieval_used": True,
                "retrieved_artwork_count": len(retrieved_artworks),
            },
        )

    return ResolvedContext(
        context_source="no_external_context",
        subject_reference=None,
        sources=[],
        prompt_payload={
            "artwork": None,
            "rag_results": [],
            "retrieved_artworks": [],
        },
        debug_payload={},
    )

def docent_build_prompt_from_context(
    user_input: str,
    dialogue_history: list[DialogueTurn],
    resolved_context: ResolvedContext,
) -> str:
    payload = resolved_context.prompt_payload

    return docent_build_prompt(
        user_input=user_input,
        dialogue_history=dialogue_history,
        artwork=payload.get("artwork"),
        retrieved_artworks=payload.get("retrieved_artworks", []),
        rag_results=payload.get("rag_results", []),
    )

docent_query_engine = QueryEngine(
    subject_resolver=docent_resolve_context,
    prompt_builder=docent_build_prompt_from_context,
)