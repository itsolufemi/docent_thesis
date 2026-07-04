from backend_python.docent.schemas.artwork_schemas import Artwork
from backend_python.extensions.retrieval.schemas.documents_schemas import RetrievalDocument


def artwork_to_retrieval_document(
    artwork: Artwork,
) -> RetrievalDocument:
    text = f"""
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
Date: {artwork.date or "unknown"}
School: {getattr(artwork, "school", None) or "unknown"}
Medium: {artwork.medium or "unknown"}
Room: {getattr(artwork, "room_name", None) or artwork.room or "unknown"}
Description: {artwork.description or "no description available"}
Provenance: {getattr(artwork, "provenance", None) or "no provenance available"}
""".strip()

    return RetrievalDocument(
        document_id=f"painting:{artwork.painting_index}",
        title=artwork.title,
        text=text,
        source_reference=f"painting:{artwork.painting_index}",
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
            "object_type": getattr(artwork, "object_type", None),
            "room": getattr(artwork, "room_name", None) or artwork.room,
        },
    )

def get_docent_retrieval_documents() -> list[RetrievalDocument]:
    artworks = get_all_artworks()

    return [
        artwork_to_retrieval_document(artwork)
        for artwork in artworks
    ]