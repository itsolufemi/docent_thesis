from __future__ import annotations

import json

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalChunk,
)
from extensions.retrieval.schemas.embedding_schemas import (
    IndexedChunkEmbedding,
)
from extensions.retrieval.schemas.index_schemas import (
    IndexedRetrievalChunk,
)
from extensions.retrieval.services.embedding_service import (
    embed_indexed_chunks,
)
from extensions.retrieval.services.index_service import (
    build_retrieval_index,
)
from extensions.retrieval.services.vector_store_service import (
    save_vector_store,
)


DocumentBuilder = Callable[
    [dict[str, Any]],
    RetrievalChunk | Iterable[RetrievalChunk],
]


def _load_json_records(
    input_path: str | Path,
) -> list[dict[str, Any]]:
    path = Path(input_path)

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "Vector-store input JSON must contain a list of records."
        )

    if not all(isinstance(record, dict) for record in data):
        raise ValueError(
            "Every vector-store input record must be a JSON object."
        )

    return data


def _build_chunks(
    records: list[dict[str, Any]],
    document_builder: DocumentBuilder,
) -> list[RetrievalChunk]:
    chunks: list[RetrievalChunk] = []

    for record in records:
        built = document_builder(record)

        if isinstance(built, RetrievalChunk):
            chunks.append(built)
        else:
            chunks.extend(built)

    return chunks


def build_vector_store(
    input_path: str | Path,
    output_path: str | Path,
    document_builder: DocumentBuilder,
    *,
    metadata_filename: str = "vector_index.json",
    embeddings_filename: str = "vector_embeddings.npy",
) -> tuple[
    list[IndexedRetrievalChunk],
    list[IndexedChunkEmbedding],
]:
    """Build and persist a vector store from JSON records."""
    records = _load_json_records(input_path)
    chunks = _build_chunks(records, document_builder)
    indexed_chunks = build_retrieval_index(chunks)
    chunk_embeddings = embed_indexed_chunks(indexed_chunks)

    output_directory = Path(output_path)
    output_directory.mkdir(parents=True, exist_ok=True)

    save_vector_store(
        indexed_chunks=indexed_chunks,
        chunk_embeddings=chunk_embeddings,
        metadata_path=(
            output_directory / metadata_filename
        ),
        embeddings_path=(
            output_directory / embeddings_filename
        ),
    )

    return indexed_chunks, chunk_embeddings
