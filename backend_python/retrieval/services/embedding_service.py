import httpx

from config import settings
from backend_python.retrieval.schemas.embedding_schemas import IndexedChunkEmbedding
from backend_python.retrieval.services.index_service import build_rag_index


def generate_embedding(text: str) -> list[float]:
    cleaned_text = text.strip()

    if not cleaned_text:
        return []

    response = httpx.post(
        f"{settings.ollama_base_url}/api/embeddings",
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
    chunk_id: str,
    embedding_text: str,
) -> IndexedChunkEmbedding:
    embedding = generate_embedding(embedding_text)

    return IndexedChunkEmbedding(
        chunk_id=chunk_id,
        embedding_text=embedding_text,
        model=settings.ollama_embedding_model,
        dimensions=len(embedding),
        embedding=embedding,
    )


def build_rag_embedding_index(
    limit: int | None = None,
) -> list[IndexedChunkEmbedding]:
    indexed_chunks = build_rag_index()

    if limit is not None:
        indexed_chunks = indexed_chunks[:limit]

    embedded_chunks = []

    for indexed_chunk in indexed_chunks:
        embedded_chunks.append(
            embed_indexed_chunk(
                chunk_id=indexed_chunk.chunk.chunk_id,
                embedding_text=indexed_chunk.embedding_text,
            )
        )

    return embedded_chunks


def summarize_rag_embedding_index(
    limit: int | None = None,
) -> dict:
    embedded_chunks = build_rag_embedding_index(limit=limit)

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