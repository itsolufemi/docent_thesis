from backend_python.conversation_core.memory.conversation_store import (
    add_dialogue_turn,
    get_recent_dialogue_history,
    get_session,
)
from backend_python.conversation_core.schemas.context_schemas import QueryDebugInfo
from backend_python.extensions.retrieval.schemas.rag_schemas import RetrievedEvidenceChunk
from backend_python.conversation_core.schemas.source_schemas import QuerySource
from backend_python.docent.services.artwork_service import get_painting_by_index
from backend_python.conversation_core.services.llm_service import generate_llm_response
from backend_python.conversation_core.services.prompt_service import build_prompt
from backend_python.extensions.retrieval.services.rag_service import retrieve_evidence_chunks_for_query
from backend_python.extensions.retrieval.services.keyword_retrieval_service import retrieve_artworks_for_query
from backend_python.docent.services.source_service import (
    build_source_from_artwork,
    build_sources_from_retrieved_artworks,
    build_sources_from_retrieved_evidence_chunks,
)


def generate_basic_response(
    text: str,
    subject_reference: str | None = None,
    conversation_id: str | None = None,
    include_debug: bool = False,
) -> tuple[str, int | None, list[QuerySource], QueryDebugInfo | None]:
    resolved_painting_index = painting_index
    context_source = "no_artwork_context"

    dialogue_history = []
    retrieved_artworks = []
    rag_results: list[RetrievedEvidenceChunk] = []
    sources: list[QuerySource] = []

    session_state = None

    if session_id is not None:
        session_state = get_session(session_id)

        if session_state is None:
            context_source = "session_not_found"
        else:
            dialogue_history = get_recent_dialogue_history(session_id)

    if resolved_painting_index is not None:
        context_source = "direct_painting_index"

    if resolved_painting_index is None and session_state is not None:
        resolved_painting_index = session_state.current_painting_index

        if resolved_painting_index is not None:
            context_source = "session_current_painting"

    artwork = None

    if resolved_painting_index is not None:
        artwork = get_painting_by_index(resolved_painting_index)

        if artwork is None:
            context_source = "painting_index_not_found"

    should_use_rag = (
        artwork is None
        and resolved_painting_index is None
    )

    if should_use_rag:
        rag_results = retrieve_evidence_chunks_for_query(
            query=text,
            limit=5,
        )

        if rag_results:
            context_source = "rag_evidence_chunks"
        else:
            context_source = "rag_no_evidence"

    should_use_record_retrieval = (
        artwork is None
        and resolved_painting_index is None
        and not rag_results
    )

    if should_use_record_retrieval:
        retrieved_artworks = retrieve_artworks_for_query(
            query=text,
            limit=3,
        )

        if retrieved_artworks:
            context_source = "retrieval_results"
        else:
            context_source = "retrieval_no_results"

    if artwork is not None:
        sources = [
            build_source_from_artwork(
                artwork=artwork,
                source_type="artwork_context",
            )
        ]

    if rag_results:
        sources = build_sources_from_retrieved_evidence_chunks(
            rag_results
        )

    if retrieved_artworks:
        sources = build_sources_from_retrieved_artworks(
            retrieved_artworks
        )

    prompt = build_prompt(
        user_input=text,
        artwork=artwork,
        dialogue_history=dialogue_history,
        retrieved_artworks=retrieved_artworks,
        rag_results=rag_results,
    )

    response = generate_llm_response(prompt)

    if session_state is not None:
        add_dialogue_turn(
            session_id=session_state.session_id,
            role="user",
            content=text,
        )

        add_dialogue_turn(
            session_id=session_state.session_id,
            role="assistant",
            content=response,
        )

    final_painting_index = (
        artwork.painting_index
        if artwork is not None
        else None
    )

    debug_info = None

    if include_debug:
        debug_info = QueryDebugInfo(
            resolved_painting_index=final_painting_index,
            context_source=context_source,
            artwork_context_used=artwork is not None,
            dialogue_turns_used=len(dialogue_history),
            prompt=prompt,
            retrieval_used=bool(retrieved_artworks),
            retrieval_results=retrieved_artworks,
            rag_used=bool(rag_results),
            rag_results=rag_results,
            sources_count=len(sources),
            sources=sources,
        )

    return response, final_painting_index, sources, debug_info