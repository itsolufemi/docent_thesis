from extensions.retrieval.schemas.chunk_schemas import RetrievalChunk
from extensions.retrieval.schemas.index_schemas import IndexedRetrievalChunk


def build_embedding_text_for_chunk(
    chunk: RetrievalChunk,
) -> str:
    metadata_text = "\n".join(
        f"{key}: {value}"
        for key, value in chunk.metadata.items()
        if value is not None
    )

    return f"""
Title: {chunk.title or "unknown"}
Chunk type: {chunk.chunk_type}
Source reference: {chunk.source_reference or "unknown"}
Parent document ID: {chunk.parent_document_id}

Metadata:
{metadata_text or "No metadata."}

Text:
{chunk.text}
""".strip()


def build_metadata_for_chunk(
    chunk: RetrievalChunk,
) -> dict[str, object]:
    return {
        **chunk.metadata,
        "chunk_id": chunk.chunk_id,
        "chunk_type": chunk.chunk_type,
        "parent_document_id": chunk.parent_document_id,
        "title": chunk.title,
        "source_reference": chunk.source_reference,
        "url": chunk.url,
    }


def build_indexed_chunk(
    chunk: RetrievalChunk,
) -> IndexedRetrievalChunk:
    return IndexedRetrievalChunk(
        chunk=chunk,
        embedding_text=build_embedding_text_for_chunk(chunk),
        metadata=build_metadata_for_chunk(chunk),
    )


def build_retrieval_index(
    chunks: list[RetrievalChunk],
) -> list[IndexedRetrievalChunk]:
    return [
        build_indexed_chunk(chunk)
        for chunk in chunks
    ]


def summarize_retrieval_index(
    indexed_chunks: list[IndexedRetrievalChunk],
) -> dict:
    chunk_types: dict[str, int] = {}
    document_ids = set()

    for indexed_chunk in indexed_chunks:
        chunk = indexed_chunk.chunk

        chunk_types[chunk.chunk_type] = (
            chunk_types.get(chunk.chunk_type, 0) + 1
        )

        document_ids.add(chunk.parent_document_id)

    return {
        "total_chunks": len(indexed_chunks),
        "chunk_types": chunk_types,
        "documents_indexed": len(document_ids),
    }