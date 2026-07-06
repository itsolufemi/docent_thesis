from backend_python.extensions.retrieval.schemas.index_schemas import IndexedRetrievalChunk
from backend_python.extensions.retrieval.schemas.rag_schemas import EvidenceChunk
from backend_python.extensions.retrieval.services.rag_service import build_all_evidence_chunks


def build_embedding_text_for_chunk(chunk: EvidenceChunk) -> str:
    return f"""
Artwork title: {chunk.title}
Artist: {chunk.artist or "unknown"}
Inventory number: {chunk.inventory_number or "unknown"}
Chunk type: {chunk.chunk_type}

Evidence text:
{chunk.text}
""".strip()


def build_metadata_for_chunk(
    chunk: EvidenceChunk,
) -> dict[str, str | int | None]:
    return {
        "chunk_id": chunk.chunk_id,
        "chunk_type": chunk.chunk_type,
        "painting_index": chunk.painting_index,
        "title": chunk.title,
        "artist": chunk.artist,
        "inventory_number": chunk.inventory_number,
        "url": chunk.url,
    }


def build_indexed_chunk(chunk: EvidenceChunk) -> IndexedRetrievalChunk:
    return IndexedRetrievalChunk(
        chunk=chunk,
        embedding_text=build_embedding_text_for_chunk(chunk),
        metadata=build_metadata_for_chunk(chunk),
    )


_rag_index_cache: list[IndexedRetrievalChunk] | None = None


def build_rag_index(
    force_reload: bool = False,
) -> list[IndexedRetrievalChunk]:
    global _rag_index_cache

    if _rag_index_cache is not None and force_reload is False:
        return _rag_index_cache

    chunks = build_all_evidence_chunks()

    _rag_index_cache = [
        build_indexed_chunk(chunk)
        for chunk in chunks
    ]

    return _rag_index_cache


def summarize_rag_index() -> dict:
    indexed_chunks = build_rag_index()

    chunk_types: dict[str, int] = {}
    artwork_indexes = set()

    for indexed_chunk in indexed_chunks:
        chunk = indexed_chunk.chunk

        chunk_types[chunk.chunk_type] = (
            chunk_types.get(chunk.chunk_type, 0) + 1
        )

        artwork_indexes.add(chunk.painting_index)

    return {
        "total_chunks": len(indexed_chunks),
        "chunk_types": chunk_types,
        "artworks_indexed": len(artwork_indexes),
    }