import re
import unicodedata

from schemas.artwork_schemas import Artwork
from schemas.retrieval_schemas import RetrievedArtwork
from services.artwork_service import get_all_artworks

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "about",
    "this",
    "that",
    "from",
    "hello",
    "hi",
    "hey",
    "yourself",
    "you",
    "are",
    "was",
    "is",
    "am",
    "i",
    "me",
    "my",
    "your",
    "please",
    "into",
    "show",
    "tell",
    "give",
    "what",
    "who",
    "why",
    "how",
    "painting",
    "artwork",
    "picture",
}


FIELD_WEIGHTS = {
    "title": 10,
    "artist": 8,
    "inventory_number": 8,
    "school": 5,
    "object_type": 5,
    "room": 4,
    "room_name": 4,
    "date": 4,
    "medium": 3,
    "themes": 6,
    "description": 3,
    "provenance": 2,
}

def normalise_text(value: str | None) -> str:
    if value is None:
        return ""
    
    value = value.lower().strip()
    value = unicodedata.normalize("NFD", value)
    value = value.encode("ascii", "ignore").decode("utf-8")
    
    return value

def tokenize_query(query: str) -> list[str]:
    normalised_query = normalise_text(query)
    tokens = re.findall(r"[a-z0-9]+", normalised_query)

    return [
        token
        for token in tokens
        if len(token) > 2 and token not in STOP_WORDS
    ]

def get_artwork_search_fields(artwork: Artwork) -> dict[str, str]:
    return {
        "title": getattr(artwork, "title", "") or "",
        "artist": getattr(artwork, "artist", "") or "",
        "school": getattr(artwork, "school", "") or "",
        "date": getattr(artwork, "date", "") or "",
        "object_type": getattr(artwork, "object_type", "") or "",
        "medium": getattr(artwork, "medium", "") or "",
        "room": getattr(artwork, "room", "") or "",
        "room_name": getattr(artwork, "room_name", "") or "",
        "description": getattr(artwork, "description", "") or "",
        "provenance": getattr(artwork, "provenance", "") or "",
        "inventory_number": getattr(artwork, "inventory_number", "") or "",
        "themes": " ".join(getattr(artwork, "themes", []) or []),
    }

def score_artwork_against_query(
    artwork: Artwork,
    query: str,
) -> tuple[int, list[str]]:
    normalised_query = normalise_text(query)
    query_terms = tokenize_query(query)

    if not query_terms and not normalised_query:
        return 0, []
    
    fields = get_artwork_search_fields(artwork)

    total_score = 0
    matched_fields = []

    for field_name, field_value in fields.items():
        normalised_field_value = normalise_text(field_value)

        if not normalised_field_value:
            continue
        
        field_score = 0
        field_weight = FIELD_WEIGHTS.get(field_name, 1)

        if normalised_query in normalised_field_value:
            field_score += field_weight * 3
        
        field_terms = set(re.findall(r"[a-z0-9]+", normalised_field_value))

        for term in query_terms:
            if term in field_terms:
                field_score += field_weight


        if field_score > 0:
            matched_fields.append(field_name)
            total_score += field_score

    return total_score, matched_fields

def build_snippet(
    artwork: Artwork,
    matched_fields: list[str],
    max_length: int = 280,
) -> str | None:
    preferred_fields = [
        "description",
        "provenance",
        "title",
        "artist",
        "school",
        "room_name",
        "room",
    ]

    fields = get_artwork_search_fields(artwork)

    for field_name in preferred_fields:
        if field_name not in matched_fields:
            continue

        value = fields.get(field_name, "").strip()

        if value:
            if len(value) <= max_length:
                return value

            return value[:max_length].rstrip() + "..."

    return None

def retrieve_artworks_for_query(
    query: str,
    limit: int = 5,
) -> list[RetrievedArtwork]:
    query = query.strip()

    query_terms = tokenize_query(query)

    if not query_terms:
        return []

    limit = max(1, min(limit, 10))

    artworks = get_all_artworks()
    results = []

    for artwork in artworks:
        score, matched_fields = score_artwork_against_query(
            artwork=artwork,
            query=query,
        )

        if score <= 0:
            continue

        results.append(
            RetrievedArtwork(
                artwork=artwork,
                score=score,
                matched_fields=matched_fields,
                snippet=build_snippet(
                    artwork=artwork,
                    matched_fields=matched_fields,
                ),
            )
        )

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )

    return results[:limit]





