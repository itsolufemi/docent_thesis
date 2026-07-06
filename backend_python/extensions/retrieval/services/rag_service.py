import re

from extensions.retrieval.schemas.chunk_schemas import (
    RetrievedChunk,
    RetrievalChunk,
)


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "who",
    "why",
    "with",
    "you",
    "your",
}


def tokenize_query(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())

    return [
        token for token in tokens
        if token not in STOP_WORDS and len(token) > 1
    ]


def chunk_search_text(
    chunk: RetrievalChunk,
) -> str:
    metadata_text = " ".join(
        str(value)
        for value in chunk.metadata.values()
        if value is not None
    )

    return " ".join(
        [
            chunk.title or "",
            chunk.chunk_type,
            chunk.text,
            chunk.source_reference or "",
            metadata_text,
        ]
    ).lower()


def score_chunk(
    chunk: RetrievalChunk,
    query_terms: list[str],
) -> tuple[int, list[str]]:
    search_text = chunk_search_text(chunk)

    matched_terms = [
        term for term in query_terms
        if term in search_text
    ]

    if not matched_terms:
        return 0, []

    score = len(matched_terms)

    if chunk.title:
        title_text = chunk.title.lower()
        score += sum(
            2 for term in matched_terms
            if term in title_text
        )

    if chunk.chunk_type:
        chunk_type_text = chunk.chunk_type.lower()
        score += sum(
            1 for term in matched_terms
            if term in chunk_type_text
        )

    return score, matched_terms


def build_chunk_snippet(
    chunk: RetrievalChunk,
    query_terms: list[str],
    max_length: int = 260,
) -> str | None:
    text = chunk.text.strip()

    if not text:
        return None

    lower_text = text.lower()
    first_match_index = None

    for term in query_terms:
        match_index = lower_text.find(term)

        if match_index != -1:
            if first_match_index is None or match_index < first_match_index:
                first_match_index = match_index

    if first_match_index is None:
        return text[:max_length]

    start = max(first_match_index - 60, 0)
    end = min(start + max_length, len(text))

    snippet = text[start:end].strip()

    if start > 0:
        snippet = "..." + snippet

    if end < len(text):
        snippet = snippet + "..."

    return snippet


def retrieve_chunks_for_query(
    query: str,
    chunks: list[RetrievalChunk],
    limit: int = 5,
) -> list[RetrievedChunk]:
    query_terms = tokenize_query(query)

    if not query_terms:
        return []

    results: list[RetrievedChunk] = []

    for chunk in chunks:
        score, matched_terms = score_chunk(
            chunk=chunk,
            query_terms=query_terms,
        )

        if score <= 0:
            continue

        results.append(
            RetrievedChunk(
                chunk=chunk,
                score=score,
                matched_terms=matched_terms,
                snippet=build_chunk_snippet(
                    chunk=chunk,
                    query_terms=query_terms,
                ),
            )
        )

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return results[:limit]