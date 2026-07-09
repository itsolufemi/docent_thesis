from collections import defaultdict

from extensions.retrieval.schemas.chunk_schemas import (
    RetrievedChunk,
    RetrievalChunk,
)


DEFAULT_CHUNK_TYPE_PRIORITY = [
    "identity",
    "description",
    "metadata",
    "provenance",
    "location",
]


def build_expansion_snippet(
    text: str,
    max_length: int = 240,
) -> str:
    cleaned_text = " ".join(text.split())

    if len(cleaned_text) <= max_length:
        return cleaned_text

    return f"{cleaned_text[:max_length].rstrip()}..."


def group_chunks_by_parent_document(
    chunks: list[RetrievalChunk],
) -> dict[str, list[RetrievalChunk]]:
    grouped_chunks: dict[str, list[RetrievalChunk]] = defaultdict(list)

    for chunk in chunks:
        grouped_chunks[chunk.parent_document_id].append(chunk)

    return dict(grouped_chunks)


def get_parent_document_order_from_results(
    retrieved_chunks: list[RetrievedChunk],
) -> list[str]:
    parent_document_ids: list[str] = []

    for retrieved_chunk in retrieved_chunks:
        parent_document_id = retrieved_chunk.chunk.parent_document_id

        if parent_document_id not in parent_document_ids:
            parent_document_ids.append(parent_document_id)

    return parent_document_ids


def get_best_score_by_parent_document(
    retrieved_chunks: list[RetrievedChunk],
) -> dict[str, float | int]:
    best_scores: dict[str, float | int] = {}

    for retrieved_chunk in retrieved_chunks:
        parent_document_id = retrieved_chunk.chunk.parent_document_id
        current_best = best_scores.get(parent_document_id)

        if current_best is None or retrieved_chunk.score > current_best:
            best_scores[parent_document_id] = retrieved_chunk.score

    return best_scores


def sort_chunks_by_type_priority(
    chunks: list[RetrievalChunk],
    chunk_type_priority: list[str],
) -> list[RetrievalChunk]:
    priority_by_type = {
        chunk_type: index
        for index, chunk_type in enumerate(chunk_type_priority)
    }

    fallback_priority = len(chunk_type_priority)

    return sorted(
        chunks,
        key=lambda chunk: (
            priority_by_type.get(chunk.chunk_type, fallback_priority),
            chunk.chunk_id,
        ),
    )


def expand_retrieved_chunks_by_parent_document(
    retrieved_chunks: list[RetrievedChunk],
    all_chunks: list[RetrievalChunk],
    limit: int = 8,
    chunk_type_priority: list[str] | None = None,
) -> list[RetrievedChunk]:
    if not retrieved_chunks:
        return []

    chunk_type_priority = chunk_type_priority or DEFAULT_CHUNK_TYPE_PRIORITY

    chunks_by_parent_document = group_chunks_by_parent_document(all_chunks)
    parent_document_order = get_parent_document_order_from_results(retrieved_chunks)
    best_score_by_parent_document = get_best_score_by_parent_document(retrieved_chunks)

    original_results_by_chunk_id = {
        retrieved_chunk.chunk.chunk_id: retrieved_chunk
        for retrieved_chunk in retrieved_chunks
    }

    expanded_results: list[RetrievedChunk] = []
    seen_chunk_ids: set[str] = set()

    for parent_document_id in parent_document_order:
        parent_chunks = chunks_by_parent_document.get(parent_document_id, [])

        ordered_parent_chunks = sort_chunks_by_type_priority(
            chunks=parent_chunks,
            chunk_type_priority=chunk_type_priority,
        )

        parent_score = best_score_by_parent_document[parent_document_id]

        for chunk in ordered_parent_chunks:
            if chunk.chunk_id in seen_chunk_ids:
                continue

            original_result = original_results_by_chunk_id.get(chunk.chunk_id)

            if original_result is not None:
                expanded_results.append(original_result)
            else:
                expanded_results.append(
                    RetrievedChunk(
                        chunk=chunk,
                        score=parent_score,
                        matched_terms=[],
                        matched_fields=["expanded_from_vector_parent"],
                        snippet=build_expansion_snippet(chunk.text),
                    )
                )

            seen_chunk_ids.add(chunk.chunk_id)

            if len(expanded_results) >= limit:
                return expanded_results

    return expanded_results