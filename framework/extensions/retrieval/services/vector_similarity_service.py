import math

from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk
from extensions.retrieval.schemas.embedding_schemas import IndexedChunkEmbedding
from extensions.retrieval.schemas.index_schemas import IndexedRetrievalChunk


def cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )

    return dot_product / (left_norm * right_norm)


def build_vector_snippet(
    text: str,
    max_length: int = 240,
) -> str:
    cleaned_text = " ".join(text.split())

    if len(cleaned_text) <= max_length:
        return cleaned_text

    return f"{cleaned_text[:max_length].rstrip()}..."


def retrieve_chunks_by_vector_similarity(
    query_embedding: list[float],
    indexed_chunks: list[IndexedRetrievalChunk],
    chunk_embeddings: list[IndexedChunkEmbedding],
    limit: int = 5,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    indexed_chunks_by_id = {
        indexed_chunk.chunk.chunk_id: indexed_chunk
        for indexed_chunk in indexed_chunks
    }

    results: list[RetrievedChunk] = []

    for chunk_embedding in chunk_embeddings:
        indexed_chunk = indexed_chunks_by_id.get(chunk_embedding.chunk_id)

        if indexed_chunk is None:
            continue

        score = cosine_similarity(
            query_embedding,
            chunk_embedding.embedding,
        )

        if score < min_score:
            continue

        results.append(
            RetrievedChunk(
                chunk=indexed_chunk.chunk,
                score=score,
                matched_terms=[],
                matched_fields=["embedding_text"],
                snippet=build_vector_snippet(indexed_chunk.chunk.text),
            )
        )

    return sorted(
        results,
        key=lambda result: result.score,
        reverse=True,
    )[:limit]