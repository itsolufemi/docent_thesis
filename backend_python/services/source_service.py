from schemas.artwork_schemas import Artwork
from schemas.retrieval_schemas import RetrievedArtwork
from schemas.source_schemas import QuerySource

def build_source_from_artwork(
    artwork: Artwork,
    source_type: str = "artwork_context",
) -> QuerySource:
    return QuerySource(
        source_type=source_type,
        painting_index=artwork.painting_index,
        title=artwork.title,
        artist=artwork.artist,
        inventory_number=getattr(artwork, "inventory_number", None),
        url=getattr(artwork, "url", None),
    )


def build_sources_from_retrieved_artworks(
    retrieved_artworks: list[RetrievedArtwork],
) -> list[QuerySource]:
    sources = []

    for retrieved in retrieved_artworks:
        artwork = retrieved.artwork

        sources.append(
            QuerySource(
                source_type="retrieved_artwork",
                painting_index=artwork.painting_index,
                title=artwork.title,
                artist=artwork.artist,
                inventory_number=getattr(artwork, "inventory_number", None),
                url=getattr(artwork, "url", None),
                matched_fields=retrieved.matched_fields,
                score=retrieved.score,
                snippet=retrieved.snippet,
            )
        )

    return sources