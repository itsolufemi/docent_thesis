from time import perf_counter

from config import settings
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalTimings,
    VectorRetrievalResult,
)
from extensions.retrieval.schemas.embedding_schemas import IndexedChunkEmbedding
from extensions.retrieval.schemas.index_schemas import IndexedRetrievalChunk
from extensions.retrieval.services.embedding_service import (
    embed_indexed_chunks,
    generate_embedding,
)
from extensions.retrieval.services.index_service import build_retrieval_index
from extensions.retrieval.services.vector_similarity_service import (
    retrieve_chunks_by_vector_similarity,
)
from extensions.retrieval.services.chunk_expansion_service import (
    expand_retrieved_chunks_by_parent_document,
)
from extensions.retrieval.services.hybrid_scoring_service import (
    rerank_retrieved_chunks_hybrid,
)
from extensions.retrieval.services.retrieval_confidence_service import (
    DEFAULT_MIN_RETRIEVAL_CONFIDENCE,
    filter_chunks_by_confidence,
)
from extensions.retrieval.services.vector_store_service import (
    load_vector_store,
    save_vector_store,
)

from docent.services.docent_retrieval_adapter import get_docent_retrieval_chunks


_docent_indexed_chunks: list[IndexedRetrievalChunk] | None = None
_docent_chunk_embeddings: list[IndexedChunkEmbedding] | None = None


def warm_up_docent_retrieval() -> dict:
    started_at = perf_counter()
    result = retrieve_docent_chunks_by_vector_similarity(
        query="The Swing",
        limit=1,
        expand_parent_documents=False,
        use_hybrid_scoring=False,
        apply_confidence_gate=False,
    )

    return {
        "seconds": round(
            perf_counter() - started_at,
            4,
        ),
        "result_count": len(result.results),
        "retrieval_timings": result.timings.model_dump(),
    }


def get_docent_vector_index(
    force_refresh: bool = False,
) -> tuple[list[IndexedRetrievalChunk], list[IndexedChunkEmbedding]]:
    global _docent_indexed_chunks
    global _docent_chunk_embeddings

    memory_cache_available = (
        _docent_indexed_chunks is not None
        and _docent_chunk_embeddings is not None
    )

    if memory_cache_available and not force_refresh:
        return _docent_indexed_chunks, _docent_chunk_embeddings

    persisted_store_available = (
        settings.docent_vector_metadata_path.exists()
        and settings.docent_vector_embeddings_path.exists()
    )

    if persisted_store_available and not force_refresh:
        _docent_indexed_chunks, _docent_chunk_embeddings = load_vector_store(
            metadata_path=settings.docent_vector_metadata_path,
            embeddings_path=settings.docent_vector_embeddings_path,
        )
        return _docent_indexed_chunks, _docent_chunk_embeddings

    chunks = get_docent_retrieval_chunks()
    _docent_indexed_chunks = build_retrieval_index(chunks)
    _docent_chunk_embeddings = embed_indexed_chunks(_docent_indexed_chunks)

    save_vector_store(
        indexed_chunks=_docent_indexed_chunks,
        chunk_embeddings=_docent_chunk_embeddings,
        metadata_path=settings.docent_vector_metadata_path,
        embeddings_path=settings.docent_vector_embeddings_path,
    )

    return _docent_indexed_chunks, _docent_chunk_embeddings

def retrieve_docent_chunks_by_vector_similarity(
    query: str,
    limit: int = 8,
    min_score: float = 0.0,
    force_refresh: bool = False,
    expand_parent_documents: bool = True,
    use_hybrid_scoring: bool = True,
    apply_confidence_gate: bool = True,
    min_confidence_score: float = DEFAULT_MIN_RETRIEVAL_CONFIDENCE,
) -> VectorRetrievalResult:
    total_started_at = perf_counter()
    timings = RetrievalTimings()

    query_embedding_started_at = perf_counter()
    query_embedding = generate_embedding(query)
    timings.query_embedding_seconds = round(
        perf_counter() - query_embedding_started_at,
        4,
    )

    if not query_embedding:
        timings.total_seconds = round(
            perf_counter() - total_started_at,
            4,
        )
        return VectorRetrievalResult(
            results=[],
            timings=timings,
        )

    memory_cache_available = (
        _docent_indexed_chunks is not None
        and _docent_chunk_embeddings is not None
    )
    persisted_store_available = (
        settings.docent_vector_metadata_path.exists()
        and settings.docent_vector_embeddings_path.exists()
    )

    if force_refresh:
        vector_index_source = "rebuilt"
    elif memory_cache_available:
        vector_index_source = "memory"
    elif persisted_store_available:
        vector_index_source = "disk"
    else:
        vector_index_source = "rebuilt"

    vector_index_started_at = perf_counter()
    indexed_chunks, chunk_embeddings = get_docent_vector_index(
        force_refresh=force_refresh,
    )
    timings.vector_index_seconds = round(
        perf_counter() - vector_index_started_at,
        4,
    )
    timings.vector_index_source = vector_index_source
    timings.vector_index_rebuilt = vector_index_source == "rebuilt"

    vector_similarity_started_at = perf_counter()
    retrieved_chunks = retrieve_chunks_by_vector_similarity(
        query_embedding=query_embedding,
        indexed_chunks=indexed_chunks,
        chunk_embeddings=chunk_embeddings,
        limit=limit,
        min_score=min_score,
    )
    timings.vector_similarity_seconds = round(
        perf_counter() - vector_similarity_started_at,
        4,
    )

    if expand_parent_documents:
        parent_expansion_started_at = perf_counter()
        all_chunks = [
            indexed_chunk.chunk
            for indexed_chunk in indexed_chunks
        ]

        retrieved_chunks = expand_retrieved_chunks_by_parent_document(
            retrieved_chunks=retrieved_chunks,
            all_chunks=all_chunks,
            limit=limit,
        )
        timings.parent_expansion_seconds = round(
            perf_counter() - parent_expansion_started_at,
            4,
        )

    if use_hybrid_scoring:
        hybrid_started_at = perf_counter()
        retrieved_chunks = rerank_retrieved_chunks_hybrid(
            query=query,
            retrieved_chunks=retrieved_chunks,
            limit=limit,
        )
        timings.hybrid_reranking_seconds = round(
            perf_counter() - hybrid_started_at,
            4,
        )

    if apply_confidence_gate:
        confidence_started_at = perf_counter()
        retrieved_chunks = filter_chunks_by_confidence(
            retrieved_chunks=retrieved_chunks,
            min_score=min_confidence_score,
        )
        timings.confidence_filter_seconds = round(
            perf_counter() - confidence_started_at,
            4,
        )

    timings.total_seconds = round(
        perf_counter() - total_started_at,
        4,
    )

    return VectorRetrievalResult(
        results=retrieved_chunks,
        timings=timings,
    )

def summarize_docent_vector_index(
    force_refresh: bool = False,
) -> dict:
    indexed_chunks, chunk_embeddings = get_docent_vector_index(
        force_refresh=force_refresh,
    )

    dimensions = 0

    if chunk_embeddings:
        dimensions = chunk_embeddings[0].dimensions

    return {
        "total_chunks": len(indexed_chunks),
        "total_vectors": len(chunk_embeddings),
        "dimensions": dimensions,
    }
