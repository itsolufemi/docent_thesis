from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk


DEFAULT_MIN_RETRIEVAL_CONFIDENCE = 0.40


def get_top_retrieval_score(
    retrieved_chunks: list[RetrievedChunk],
) -> float:
    if not retrieved_chunks:
        return 0.0

    return max(
        float(retrieved_chunk.score)
        for retrieved_chunk in retrieved_chunks
    )


def filter_chunks_by_confidence(
    retrieved_chunks: list[RetrievedChunk],
    min_score: float = DEFAULT_MIN_RETRIEVAL_CONFIDENCE,
) -> list[RetrievedChunk]:
    return [
        retrieved_chunk
        for retrieved_chunk in retrieved_chunks
        if float(retrieved_chunk.score) >= min_score
    ]


def has_retrieval_confidence(
    retrieved_chunks: list[RetrievedChunk],
    min_score: float = DEFAULT_MIN_RETRIEVAL_CONFIDENCE,
) -> bool:
    return get_top_retrieval_score(retrieved_chunks) >= min_score