from conversation_core.schemas.conversation_schemas import DialogueTurn
from conversation_core.schemas.query_schemas import ResolvedContext
from conversation_core.schemas.source_schemas import QuerySource
from conversation_core.services.query_service import QueryEngine

from docent.services.artwork_service import get_painting_by_index
from docent.services.docent_prompt_service import docent_build_prompt
from docent.services.docent_retrieval_adapter import (
    get_docent_retrieval_chunks,
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
from extensions.retrieval.services.rag_service import (
    retrieve_chunks_for_query,
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
                        "retrieved_chunks": [],
                        "retrieved_documents": [],
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

    chunks = get_docent_retrieval_chunks()

    retrieved_chunks = retrieve_chunks_for_query(
        query=user_input,
        chunks=chunks,
        limit=5,
    )

    if retrieved_chunks:
        return ResolvedContext(
            context_source="retrieved_chunks",
            subject_reference=None,
            sources=build_sources_from_retrieved_chunks(retrieved_chunks),
            prompt_payload={
                "artwork": None,
                "retrieved_chunks": retrieved_chunks,
                "retrieved_documents": [],
            },
            debug_payload={
                "chunk_retrieval_used": True,
                "retrieved_chunk_count": len(retrieved_chunks),
            },
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
                "artwork": None,
                "retrieved_chunks": [],
                "retrieved_documents": retrieved_documents,
            },
            debug_payload={
                "document_retrieval_used": True,
                "retrieved_document_count": len(retrieved_documents),
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
        retrieved_documents=payload.get("retrieved_documents", []),
        retrieved_chunks=payload.get("retrieved_chunks", []),
    )


docent_query_engine = QueryEngine(
    subject_resolver=docent_resolve_context,
    prompt_builder=docent_build_prompt_from_context,
)