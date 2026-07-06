from docent.schemas.artwork_schemas import Artwork
from docent.services.artwork_service import get_all_artworks
from backend_python.extensions.retrieval.schemas.chunk_schemas import RetrievalChunk
from backend_python.extensions.retrieval.schemas.document_schemas import RetrievalDocument


def artwork_as_subject_get_reference(
    artwork: Artwork,
) -> str:
    return f"painting:{artwork.painting_index}"


def artwork_to_retrieval_document(
    artwork: Artwork,
) -> RetrievalDocument:
    source_reference = artwork_as_subject_get_reference(artwork)

    text = f"""
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
Date: {artwork.date or "unknown"}
School: {getattr(artwork, "school", None) or "unknown"}
Object type: {getattr(artwork, "object_type", None) or "unknown"}
Medium: {artwork.medium or "unknown"}
Room: {getattr(artwork, "room_name", None) or artwork.room or "unknown"}
Description: {artwork.description or "no description available"}
Provenance: {getattr(artwork, "provenance", None) or "no provenance available"}
""".strip()

    return RetrievalDocument(
        document_id=source_reference,
        title=artwork.title,
        text=text,
        source_reference=source_reference,
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
            "school": getattr(artwork, "school", None),
            "object_type": getattr(artwork, "object_type", None),
            "medium": artwork.medium,
            "room": getattr(artwork, "room_name", None) or artwork.room,
        },
    )


def get_docent_retrieval_documents() -> list[RetrievalDocument]:
    artworks = get_all_artworks()

    return [
        artwork_to_retrieval_document(artwork)
        for artwork in artworks
    ]


def build_identity_chunk(
    artwork: Artwork,
) -> RetrievalChunk:
    source_reference = artwork_as_subject_get_reference(artwork)

    text = f"""
{artwork.title} is an artwork by {artwork.artist or "an unknown artist"}.
Date: {artwork.date or "unknown"}.
School: {getattr(artwork, "school", None) or "unknown"}.
Object type: {getattr(artwork, "object_type", None) or "unknown"}.
""".strip()

    return RetrievalChunk(
        chunk_id=f"{source_reference}:identity",
        chunk_type="identity",
        parent_document_id=source_reference,
        title=artwork.title,
        text=text,
        source_reference=source_reference,
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
        },
    )


def build_description_chunk(
    artwork: Artwork,
) -> RetrievalChunk | None:
    if not artwork.description:
        return None

    source_reference = artwork_as_subject_get_reference(artwork)

    return RetrievalChunk(
        chunk_id=f"{source_reference}:description",
        chunk_type="description",
        parent_document_id=source_reference,
        title=artwork.title,
        text=artwork.description,
        source_reference=source_reference,
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
        },
    )


def build_provenance_chunk(
    artwork: Artwork,
) -> RetrievalChunk | None:
    provenance = getattr(artwork, "provenance", None)

    if not provenance:
        return None

    source_reference = artwork_as_subject_get_reference(artwork)

    return RetrievalChunk(
        chunk_id=f"{source_reference}:provenance",
        chunk_type="provenance",
        parent_document_id=source_reference,
        title=artwork.title,
        text=provenance,
        source_reference=source_reference,
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
        },
    )


def build_location_chunk(
    artwork: Artwork,
) -> RetrievalChunk | None:
    room = getattr(artwork, "room_name", None) or artwork.room

    if not room:
        return None

    source_reference = artwork_as_subject_get_reference(artwork)

    text = f"""
{artwork.title} is located in {room}.
""".strip()

    return RetrievalChunk(
        chunk_id=f"{source_reference}:location",
        chunk_type="location",
        parent_document_id=source_reference,
        title=artwork.title,
        text=text,
        source_reference=source_reference,
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
            "room": room,
        },
    )


def build_metadata_chunk(
    artwork: Artwork,
) -> RetrievalChunk:
    source_reference = artwork_as_subject_get_reference(artwork)

    text = f"""
Title: {artwork.title}
Artist: {artwork.artist or "unknown"}
Date: {artwork.date or "unknown"}
Medium: {artwork.medium or "unknown"}
School: {getattr(artwork, "school", None) or "unknown"}
Inventory number: {getattr(artwork, "inventory_number", None) or "unknown"}
""".strip()

    return RetrievalChunk(
        chunk_id=f"{source_reference}:metadata",
        chunk_type="metadata",
        parent_document_id=source_reference,
        title=artwork.title,
        text=text,
        source_reference=source_reference,
        url=getattr(artwork, "url", None),
        metadata={
            "painting_index": artwork.painting_index,
            "artist": artwork.artist,
            "inventory_number": getattr(artwork, "inventory_number", None),
        },
    )


def artwork_to_retrieval_chunks(
    artwork: Artwork,
) -> list[RetrievalChunk]:
    possible_chunks = [
        build_identity_chunk(artwork),
        build_description_chunk(artwork),
        build_provenance_chunk(artwork),
        build_location_chunk(artwork),
        build_metadata_chunk(artwork),
    ]

    return [
        chunk for chunk in possible_chunks
        if chunk is not None
    ]


def get_docent_retrieval_chunks() -> list[RetrievalChunk]:
    chunks: list[RetrievalChunk] = []

    for artwork in get_all_artworks():
        chunks.extend(
            artwork_to_retrieval_chunks(artwork)
        )

    return chunks