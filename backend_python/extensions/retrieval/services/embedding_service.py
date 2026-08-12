from config import settings
from conversation_core.services.ollama_http_client import (
    ollama_http_client,
)
from extensions.retrieval.schemas.embedding_schemas import IndexedChunkEmbedding
from extensions.retrieval.schemas.index_schemas import IndexedRetrievalChunk


def generate_embedding(text: str) -> list[float]:
    cleaned_text = text.strip()

    if not cleaned_text:
        return []

    response = ollama_http_client.post(
        "/api/embeddings",
        json={
            "model": settings.ollama_embedding_model,
            "prompt": cleaned_text,
        },
        timeout=60.0,
    )

    response.raise_for_status()

    data = response.json()

    return data.get("embedding", [])


def embed_indexed_chunk(
    indexed_chunk: IndexedRetrievalChunk,
) -> IndexedChunkEmbedding:
    embedding = generate_embedding(indexed_chunk.embedding_text)

    return IndexedChunkEmbedding(
        chunk_id=indexed_chunk.chunk.chunk_id,
        embedding_text=indexed_chunk.embedding_text,
        model=settings.ollama_embedding_model,
        dimensions=len(embedding),
        embedding=embedding,
    )


def embed_indexed_chunks(
    indexed_chunks: list[IndexedRetrievalChunk],
    limit: int | None = None,
) -> list[IndexedChunkEmbedding]:
    if limit is not None:
        indexed_chunks = indexed_chunks[:limit]

    return [
        embed_indexed_chunk(indexed_chunk)
        for indexed_chunk in indexed_chunks
    ]


def summarize_embedded_chunks(
    embedded_chunks: list[IndexedChunkEmbedding],
) -> dict:
    if not embedded_chunks:
        return {
            "total_vectors": 0,
            "dimensions": 0,
            "model": settings.ollama_embedding_model,
        }

    return {
        "total_vectors": len(embedded_chunks),
        "dimensions": embedded_chunks[0].dimensions,
        "model": settings.ollama_embedding_model,
    }
