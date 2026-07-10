from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
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

from docent.services.docent_retrieval_adapter import get_docent_retrieval_chunks


_docent_indexed_chunks: list[IndexedRetrievalChunk] | None = None
_docent_chunk_embeddings: list[IndexedChunkEmbedding] | None = None


def get_docent_vector_index(
    force_refresh: bool = False,
) -> tuple[list[IndexedRetrievalChunk], list[IndexedChunkEmbedding]]:
    global _docent_indexed_chunks
    global _docent_chunk_embeddings

    if (
        force_refresh
        or _docent_indexed_chunks is None
        or _docent_chunk_embeddings is None
    ):
        chunks = get_docent_retrieval_chunks()
        _docent_indexed_chunks = build_retrieval_index(chunks)
        _docent_chunk_embeddings = embed_indexed_chunks(_docent_indexed_chunks)

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
) -> list[RetrievedChunk]:
    query_embedding = generate_embedding(query)

    if not query_embedding:
        return []

    indexed_chunks, chunk_embeddings = get_docent_vector_index(
        force_refresh=force_refresh,
    )

    vector_results = retrieve_chunks_by_vector_similarity(
        query_embedding=query_embedding,
        indexed_chunks=indexed_chunks,
        chunk_embeddings=chunk_embeddings,
        limit=limit,
        min_score=min_score,
    )

    if expand_parent_documents:
        all_chunks = [
            indexed_chunk.chunk
            for indexed_chunk in indexed_chunks
        ]

        retrieved_chunks = expand_retrieved_chunks_by_parent_document(
            retrieved_chunks=vector_results,
            all_chunks=all_chunks,
            limit=limit,
        )
    else:
        retrieved_chunks = vector_results

    if use_hybrid_scoring:
        retrieved_chunks = rerank_retrieved_chunks_hybrid(
            query=query,
            retrieved_chunks=retrieved_chunks,
            limit=limit,
        )

    if not apply_confidence_gate:
        return retrieved_chunks

    return filter_chunks_by_confidence(
        retrieved_chunks=retrieved_chunks,
        min_score=min_confidence_score,
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