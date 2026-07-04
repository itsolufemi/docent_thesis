import re

from backend_python.docent.schemas.artwork_schemas import Artwork
from backend_python.extensions.retrieval.schemas.rag_schemas import EvidenceChunk, RetrievedEvidenceChunk
from backend_python.docent.services.artwork_service import get_all_artworks
from backend_python.extensions.retrieval.services.keyword_retrieval_service import normalise_text, tokenize_query


CHUNK_TYPE_WEIGHTS = {
    "identity": 8,
    "description": 5,
    "provenance": 5,
    "location": 4,
    "metadata": 4,
}


def build_chunk_id(
    painting_index: int,
    chunk_type: str,
) -> str:
    return f"{painting_index}-{chunk_type}"


def build_evidence_chunk(
    artwork: Artwork,
    chunk_type: str,
    text: str,
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=build_chunk_id(
            painting_index=artwork.painting_index,
            chunk_type=chunk_type,
        ),
        chunk_type=chunk_type,
        painting_index=artwork.painting_index,
        title=artwork.title,
        artist=artwork.artist,
        inventory_number=getattr(artwork, "inventory_number", None),
        url=getattr(artwork, "url", None),
        text=text.strip(),
    )


def build_identity_chunk(artwork: Artwork) -> EvidenceChunk:
    text = f"""
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
Date: {artwork.date or "unknown"}
Object type: {getattr(artwork, "object_type", None) or "unknown"}
Inventory number: {getattr(artwork, "inventory_number", None) or "unknown"}
""".strip()

    return build_evidence_chunk(
        artwork=artwork,
        chunk_type="identity",
        text=text,
    )


def build_description_chunk(artwork: Artwork) -> EvidenceChunk | None:
    if not artwork.description:
        return None

    return build_evidence_chunk(
        artwork=artwork,
        chunk_type="description",
        text=artwork.description,
    )


def build_provenance_chunk(artwork: Artwork) -> EvidenceChunk | None:
    provenance = getattr(artwork, "provenance", None)

    if not provenance:
        return None

    return build_evidence_chunk(
        artwork=artwork,
        chunk_type="provenance",
        text=provenance,
    )


def build_location_chunk(artwork: Artwork) -> EvidenceChunk | None:
    room = getattr(artwork, "room_name", None) or artwork.room
    room_index = getattr(artwork, "room_index", None)

    if not room and room_index is None:
        return None

    text = f"""
Room: {room or "unknown"}
Room index: {room_index if room_index is not None else "unknown"}
""".strip()

    return build_evidence_chunk(
        artwork=artwork,
        chunk_type="location",
        text=text,
    )


def build_metadata_chunk(artwork: Artwork) -> EvidenceChunk:
    text = f"""
School: {getattr(artwork, "school", None) or "unknown"}
Date: {artwork.date or "unknown"}
Medium: {artwork.medium or "unknown"}
Object type: {getattr(artwork, "object_type", None) or "unknown"}
""".strip()

    return build_evidence_chunk(
        artwork=artwork,
        chunk_type="metadata",
        text=text,
    )


def build_evidence_chunks_for_artwork(
    artwork: Artwork,
) -> list[EvidenceChunk]:
    possible_chunks = [
        build_identity_chunk(artwork),
        build_description_chunk(artwork),
        build_provenance_chunk(artwork),
        build_location_chunk(artwork),
        build_metadata_chunk(artwork),
    ]

    return [
        chunk
        for chunk in possible_chunks
        if chunk is not None and chunk.text
    ]


def build_all_evidence_chunks() -> list[EvidenceChunk]:
    artworks = get_all_artworks()
    chunks = []

    for artwork in artworks:
        chunks.extend(
            build_evidence_chunks_for_artwork(artwork)
        )

    return chunks


def get_chunk_search_text(chunk: EvidenceChunk) -> str:
    return " ".join(
        [
            chunk.title or "",
            chunk.artist or "",
            chunk.inventory_number or "",
            chunk.chunk_type,
            chunk.text or "",
        ]
    )


def score_chunk_against_query(
    chunk: EvidenceChunk,
    query: str,
) -> tuple[int, list[str]]:
    query_terms = tokenize_query(query)

    if not query_terms:
        return 0, []

    normalised_query = normalise_text(query)
    normalised_chunk_text = normalise_text(
        get_chunk_search_text(chunk)
    )

    chunk_terms = set(
        re.findall(r"[a-z0-9]+", normalised_chunk_text)
    )

    score = 0
    matched_terms = []

    chunk_weight = CHUNK_TYPE_WEIGHTS.get(
        chunk.chunk_type,
        1,
    )

    if normalised_query in normalised_chunk_text:
        score += chunk_weight * 3

    for term in query_terms:
        if term in chunk_terms:
            matched_terms.append(term)
            score += chunk_weight

    return score, matched_terms


def retrieve_evidence_chunks_for_query(
    query: str,
    limit: int = 5,
) -> list[RetrievedEvidenceChunk]:
    query = query.strip()
    query_terms = tokenize_query(query)

    if not query_terms:
        return []

    limit = max(1, min(limit, 10))

    chunks = build_all_evidence_chunks()
    results = []

    for chunk in chunks:
        score, matched_terms = score_chunk_against_query(
            chunk=chunk,
            query=query,
        )

        if score <= 0:
            continue

        results.append(
            RetrievedEvidenceChunk(
                chunk=chunk,
                score=score,
                matched_terms=matched_terms,
            )
        )

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return results[:limit]