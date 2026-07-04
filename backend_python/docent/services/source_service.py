from backend_python.docent.schemas.artwork_schemas import Artwork
from backend_python.extensions.retrieval.schemas.rag_schemas import RetrievedEvidenceChunk
from backend_python.extensions.retrieval.schemas.keyword_retrieval_schemas import RetrievedArtwork
from backend_python.conversation_core.schemas.source_schemas import QuerySource


def build_source_from_artwork(
    artwork: Artwork,
    source_type: str = "artwork_context",
) -> QuerySource:
    return QuerySource(
        source_type=source_type,
        title=artwork.title,
        reference=f"painting:{artwork.painting_index}",
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
        },
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
                title=artwork.title,
                reference=f"painting:{artwork.painting_index}",
                url=getattr(artwork, "url", None),
                score=retrieved.score,
                snippet=retrieved.snippet,
                metadata={
                    "painting_index": artwork.painting_index,
                    "artist": artwork.artist,
                    "inventory_number": getattr(artwork, "inventory_number", None),
                    "matched_fields": retrieved.matched_fields,
                },
            )
        )

    return sources


def build_sources_from_retrieved_evidence_chunks(
    retrieved_chunks: list[RetrievedEvidenceChunk],
) -> list[QuerySource]:
    sources = []

    for retrieved in retrieved_chunks:
        chunk = retrieved.chunk

        sources.append(
            QuerySource(
                source_type="evidence_chunk",
                title=chunk.title,
                reference=f"chunk:{chunk.chunk_id}",
                url=chunk.url,
                score=retrieved.score,
                snippet=chunk.text,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "chunk_type": chunk.chunk_type,
                    "painting_index": chunk.painting_index,
                    "artist": chunk.artist,
                    "inventory_number": chunk.inventory_number,
                    "matched_terms": retrieved.matched_terms,
                },
            )
        )

    return sources