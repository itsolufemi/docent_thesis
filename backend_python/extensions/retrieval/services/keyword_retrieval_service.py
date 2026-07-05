import re

from backend_python.extensions.retrieval.schemas.document_schemas import (
    RetrievedDocument,
    RetrievalDocument,
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


def normalise_text(text: str) -> str:
    return text.lower()


def tokenize_query(query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())

    return [
        token for token in tokens
        if token not in STOP_WORDS and len(token) > 1
    ]


def document_search_fields(
    document: RetrievalDocument,
) -> dict[str, str]:
    metadata_text = " ".join(
        str(value)
        for value in document.metadata.values()
        if value is not None
    )

    return {
        "title": document.title or "",
        "text": document.text,
        "source_reference": document.source_reference or "",
        "metadata": metadata_text,
    }


FIELD_WEIGHTS = {
    "title": 6,
    "source_reference": 5,
    "text": 3,
    "metadata": 2,
}


def score_document(
    document: RetrievalDocument,
    query_terms: list[str],
) -> tuple[int, list[str]]:
    fields = document_search_fields(document)

    score = 0
    matched_fields: list[str] = []

    for field_name, field_text in fields.items():
        normalised_field = normalise_text(field_text)
        field_tokens = set(
            re.findall(r"[a-zA-Z0-9]+", normalised_field)
        )

        field_matched = False

        for term in query_terms:
            if term in field_tokens:
                score += FIELD_WEIGHTS.get(field_name, 1)
                field_matched = True

        if field_matched:
            matched_fields.append(field_name)

    return score, matched_fields


def build_snippet(
    document: RetrievalDocument,
    query_terms: list[str],
    max_length: int = 220,
) -> str | None:
    text = document.text.strip()

    if not text:
        return None

    lower_text = text.lower()

    first_match_index = None

    for term in query_terms:
        match_index = lower_text.find(term.lower())

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


def retrieve_documents_by_keyword(
    query: str,
    documents: list[RetrievalDocument],
    limit: int = 5,
) -> list[RetrievedDocument]:
    query_terms = tokenize_query(query)

    if not query_terms:
        return []

    results: list[RetrievedDocument] = []

    for document in documents:
        score, matched_fields = score_document(
            document=document,
            query_terms=query_terms,
        )

        if score <= 0:
            continue

        results.append(
            RetrievedDocument(
                document=document,
                score=score,
                matched_terms=query_terms,
                matched_fields=matched_fields,
                snippet=build_snippet(
                    document=document,
                    query_terms=query_terms,
                ),
            )
        )

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return results[:limit]