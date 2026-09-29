from __future__ import annotations

from typing import Literal

from docent.config.discovery_config import (
    DISCOVERY_CANDIDATE_LIMIT,
    DISCOVERY_EVIDENCE_PER_ARTWORK,
    DISCOVERY_MIN_CONFIDENCE,
    DISCOVERY_PROXIMITY_SCORE_BAND,
    DISCOVERY_RETRIEVAL_LIMIT,
)
from docent.services.artwork_service import get_painting_by_index
from docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
)


DiscoveryScope = Literal["current_artwork", "collection"]


def _painting_index(reference: str, metadata: dict) -> int | None:
    value = metadata.get("painting_index")

    try:
        return int(value) if value is not None else int(reference.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        return None


def _room_distance(
    current_room_index: int | None,
    candidate_room_index: int | None,
) -> int | None:
    if current_room_index is None or candidate_room_index is None:
        return None

    return abs(candidate_room_index - current_room_index)


def _rank_candidates(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    strongest_score = max(candidate["semantic_score"] for candidate in candidates)
    proximity_band = [
        candidate
        for candidate in candidates
        if candidate["semantic_score"] >= (
            strongest_score - DISCOVERY_PROXIMITY_SCORE_BAND
        )
    ]
    remaining = [
        candidate
        for candidate in candidates
        if candidate not in proximity_band
    ]
    proximity_band.sort(
        key=lambda candidate: (
            candidate["room_distance"] is None,
            candidate["room_distance"] or 0,
            -candidate["semantic_score"],
        )
    )
    remaining.sort(
        key=lambda candidate: -candidate["semantic_score"]
    )
    return [*proximity_band, *remaining]


def discover_docent_candidates(
    *,
    query: str,
    scope: DiscoveryScope,
    current_reference: str | None,
    excluded_references: set[str] | None = None,
) -> dict:
    allowed_references = (
        {current_reference}
        if scope == "current_artwork" and current_reference
        else None
    )
    exclusions = set(excluded_references or [])

    if scope == "collection" and current_reference:
        exclusions.add(current_reference)

    if scope == "current_artwork" and not current_reference:
        return {
            "query": query,
            "scope": scope,
            "current_reference": None,
            "candidates": [],
            "retrieval_performed": False,
            "retrieval_timings": None,
        }

    retrieval = retrieve_docent_chunks_by_vector_similarity(
        query=query,
        limit=DISCOVERY_RETRIEVAL_LIMIT,
        expand_parent_documents=False,
        use_hybrid_scoring=False,
        apply_confidence_gate=True,
        min_confidence_score=DISCOVERY_MIN_CONFIDENCE,
        allowed_references=allowed_references,
        excluded_references=(
            exclusions if scope == "collection" else None
        ),
        allowed_chunk_types=(
            {"description", "provenance"}
            if scope == "current_artwork"
            else {"description"}
        ),
    )

    current_artwork = None
    if current_reference:
        current_index = _painting_index(current_reference, {})
        if current_index is not None:
            current_artwork = get_painting_by_index(current_index)

    grouped: dict[str, list] = {}
    for retrieved in retrieval.results:
        reference = (
            retrieved.chunk.source_reference
            or retrieved.chunk.parent_document_id
        )
        if reference:
            grouped.setdefault(reference, []).append(retrieved)

    candidates: list[dict] = []
    for reference, evidence_results in grouped.items():
        best = evidence_results[0]
        painting_index = _painting_index(reference, best.chunk.metadata)
        artwork = (
            get_painting_by_index(painting_index)
            if painting_index is not None
            else None
        )
        if artwork is None:
            continue

        candidate_evidence = [
            {
                "chunk_id": item.chunk.chunk_id,
                "chunk_type": item.chunk.chunk_type,
                "text": item.chunk.text,
                "score": float(item.score),
                "url": item.chunk.url,
            }
            for item in evidence_results[:DISCOVERY_EVIDENCE_PER_ARTWORK]
        ]
        candidates.append(
            {
                "painting_index": artwork.painting_index,
                "reference": reference,
                "title": artwork.title,
                "artist": artwork.artist,
                "semantic_score": float(best.score),
                "room_index": artwork.room_index,
                "room_name": artwork.room_name or artwork.room,
                "room_distance": _room_distance(
                    current_artwork.room_index if current_artwork else None,
                    artwork.room_index,
                ),
                "evidence": candidate_evidence,
            }
        )

    return {
        "query": query,
        "scope": scope,
        "current_reference": current_reference,
        "candidates": _rank_candidates(candidates)[
            :DISCOVERY_CANDIDATE_LIMIT
        ],
        "retrieval_performed": True,
        "retrieval_timings": retrieval.timings.model_dump(mode="json"),
    }
