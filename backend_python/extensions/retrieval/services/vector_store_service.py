import json
from pathlib import Path

import numpy as np

from extensions.retrieval.schemas.embedding_schemas import IndexedChunkEmbedding
from extensions.retrieval.schemas.index_schemas import IndexedRetrievalChunk


def save_vector_store(
    *,
    indexed_chunks: list[IndexedRetrievalChunk],
    chunk_embeddings: list[IndexedChunkEmbedding],
    metadata_path: Path,
    embeddings_path: Path,
) -> None:
    """Persist indexed chunk metadata and its ordered embedding matrix."""
    if len(indexed_chunks) != len(chunk_embeddings):
        raise ValueError(
            "The number of indexed chunks must match the number of chunk embeddings."
        )

    for indexed_chunk, chunk_embedding in zip(
        indexed_chunks,
        chunk_embeddings,
        strict=True,
    ):
        if indexed_chunk.chunk.chunk_id != chunk_embedding.chunk_id:
            raise ValueError(
                "Chunk and embedding order do not match: "
                f"{indexed_chunk.chunk.chunk_id} != {chunk_embedding.chunk_id}"
            )

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    embeddings_path.parent.mkdir(parents=True, exist_ok=True)

    metadata_payload = {
        "embedding_model": chunk_embeddings[0].model if chunk_embeddings else None,
        "total_chunks": len(indexed_chunks),
        "indexed_chunks": [chunk.model_dump() for chunk in indexed_chunks],
        "embedding_records": [
            {
                "chunk_id": embedding.chunk_id,
                "embedding_text": embedding.embedding_text,
                "model": embedding.model,
                "dimensions": embedding.dimensions,
            }
            for embedding in chunk_embeddings
        ],
    }

    metadata_path.write_text(
        json.dumps(metadata_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if chunk_embeddings:
        embedding_matrix = np.asarray(
            [embedding.embedding for embedding in chunk_embeddings],
            dtype=np.float32,
        )
    else:
        embedding_matrix = np.empty(shape=(0, 0), dtype=np.float32)

    np.save(embeddings_path, embedding_matrix)


def load_vector_store(
    *,
    metadata_path: Path,
    embeddings_path: Path,
) -> tuple[list[IndexedRetrievalChunk], list[IndexedChunkEmbedding]]:
    """Load and validate a previously persisted vector index."""
    if not metadata_path.exists():
        raise FileNotFoundError(f"Vector metadata file not found: {metadata_path}")
    if not embeddings_path.exists():
        raise FileNotFoundError(f"Vector embeddings file not found: {embeddings_path}")

    metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    indexed_chunks = [
        IndexedRetrievalChunk.model_validate(item)
        for item in metadata_payload.get("indexed_chunks", [])
    ]
    embedding_records = metadata_payload.get("embedding_records", [])
    embedding_matrix = np.load(embeddings_path, allow_pickle=False)

    if len(indexed_chunks) != len(embedding_records):
        raise ValueError(
            "Stored indexed chunks and embedding metadata have different lengths."
        )
    if len(embedding_records) != len(embedding_matrix):
        raise ValueError(
            "Stored embedding metadata and NumPy vector matrix have different lengths."
        )

    chunk_embeddings: list[IndexedChunkEmbedding] = []
    for row_index, record in enumerate(embedding_records):
        vector = embedding_matrix[row_index].tolist()
        embedding = IndexedChunkEmbedding(
            chunk_id=record["chunk_id"],
            embedding_text=record["embedding_text"],
            model=record["model"],
            dimensions=len(vector),
            embedding=vector,
        )

        corresponding_chunk = indexed_chunks[row_index]
        if corresponding_chunk.chunk.chunk_id != embedding.chunk_id:
            raise ValueError("Stored chunk and embedding order do not match.")

        chunk_embeddings.append(embedding)

    return indexed_chunks, chunk_embeddings
