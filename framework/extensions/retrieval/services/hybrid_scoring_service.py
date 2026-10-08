import re

from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "about",
    "by",
    "for",
    "from",
    "give",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "show",
    "something",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
}


DEFAULT_CHUNK_TYPE_WEIGHTS = {
    "description": 1.0,
    "identity": 0.9,
    "metadata": 0.75,
    "provenance": 0.7,
    "location": 0.45,
}


LOCATION_QUERY_TERMS = {
    "where",
    "located",
    "location",
    "room",
    "find",
}


def tokenize_text(
    text: str,
) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return [
        token
        for token in tokens
        if token not in STOP_WORDS
    ]


def metadata_to_search_text(
    metadata: dict[str, object],
) -> str:
    values: list[str] = []

    for value in metadata.values():
        if value is None:
            continue

        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))

    return " ".join(values)


def build_chunk_search_text(
    retrieved_chunk: RetrievedChunk,
) -> str:
    chunk = retrieved_chunk.chunk

    return " ".join(
        [
            chunk.title or "",
            chunk.chunk_type,
            chunk.text,
            metadata_to_search_text(chunk.metadata),
        ]
    )


def get_matched_query_terms(
    query_terms: list[str],
    search_text: str,
) -> list[str]:
    search_terms = set(tokenize_text(search_text))

    return [
        term
        for term in query_terms
        if term in search_terms
    ]


def score_keyword_overlap(
    query_terms: list[str],
    matched_terms: list[str],
) -> float:
    if not query_terms:
        return 0.0

    return len(set(matched_terms)) / len(set(query_terms))


def get_chunk_type_weights_for_query(
    query_terms: list[str],
) -> dict[str, float]:
    weights = dict(DEFAULT_CHUNK_TYPE_WEIGHTS)

    if any(term in LOCATION_QUERY_TERMS for term in query_terms):
        weights["location"] = 1.0
        weights["metadata"] = 0.8
        weights["identity"] = 0.7
        weights["description"] = 0.6

    return weights


def score_chunk_type(
    chunk_type: str,
    chunk_type_weights: dict[str, float],
) -> float:
    return chunk_type_weights.get(chunk_type, 0.5)


def normalize_vector_score(
    score: float | int,
) -> float:
    numeric_score = float(score)

    if numeric_score < 0.0:
        return 0.0

    if numeric_score > 1.0:
        return 1.0

    return numeric_score


def combine_scores(
    vector_score: float,
    keyword_score: float,
    chunk_type_score: float,
    vector_weight: float,
    keyword_weight: float,
    chunk_type_weight: float,
) -> float:
    return (
        vector_score * vector_weight
        + keyword_score * keyword_weight
        + chunk_type_score * chunk_type_weight
    )


def merge_matched_fields(
    existing_fields: list[str],
    matched_terms: list[str],
) -> list[str]:
    fields = list(existing_fields)

    if "hybrid_score" not in fields:
        fields.append("hybrid_score")

    if "chunk_type_priority" not in fields:
        fields.append("chunk_type_priority")

    if matched_terms and "keyword_text" not in fields:
        fields.append("keyword_text")

    return fields


def rerank_retrieved_chunks_hybrid(
    query: str,
    retrieved_chunks: list[RetrievedChunk],
    limit: int = 8,
    vector_weight: float = 0.65,
    keyword_weight: float = 0.2,
    chunk_type_weight: float = 0.15,
) -> list[RetrievedChunk]:
    query_terms = tokenize_text(query)

    if not retrieved_chunks:
        return []

    chunk_type_weights = get_chunk_type_weights_for_query(query_terms)
    reranked_chunks: list[RetrievedChunk] = []

    for retrieved_chunk in retrieved_chunks:
        search_text = build_chunk_search_text(retrieved_chunk)
        matched_terms = get_matched_query_terms(
            query_terms=query_terms,
            search_text=search_text,
        )

        vector_score = normalize_vector_score(retrieved_chunk.score)
        keyword_score = score_keyword_overlap(
            query_terms=query_terms,
            matched_terms=matched_terms,
        )
        chunk_type_score = score_chunk_type(
            chunk_type=retrieved_chunk.chunk.chunk_type,
            chunk_type_weights=chunk_type_weights,
        )

        hybrid_score = combine_scores(
            vector_score=vector_score,
            keyword_score=keyword_score,
            chunk_type_score=chunk_type_score,
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
            chunk_type_weight=chunk_type_weight,
        )

        combined_matched_terms = sorted(
            set(retrieved_chunk.matched_terms + matched_terms)
        )

        reranked_chunks.append(
            RetrievedChunk(
                chunk=retrieved_chunk.chunk,
                score=hybrid_score,
                matched_terms=combined_matched_terms,
                matched_fields=merge_matched_fields(
                    existing_fields=retrieved_chunk.matched_fields,
                    matched_terms=matched_terms,
                ),
                snippet=retrieved_chunk.snippet,
            )
        )

    return sorted(
        reranked_chunks,
        key=lambda chunk: chunk.score,
        reverse=True,
    )[:limit]