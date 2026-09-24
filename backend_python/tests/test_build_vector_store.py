from __future__ import annotations

import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from conversation_core.rag.build_vector_store import (
    build_vector_store,
)
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalChunk,
)
from extensions.retrieval.schemas.embedding_schemas import (
    IndexedChunkEmbedding,
)


class BuildVectorStoreTest(unittest.TestCase):
    def test_builds_store_at_supplied_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "records.json"
            output_path = root / "nested" / "vector_store"
            input_path.write_text(
                json.dumps(
                    [
                        {"id": "one", "text": "First"},
                        {"id": "two", "text": "Second"},
                    ]
                ),
                encoding="utf-8",
            )

            def document_builder(record: dict) -> RetrievalChunk:
                return RetrievalChunk(
                    chunk_id=record["id"],
                    chunk_type="test",
                    parent_document_id=record["id"],
                    text=record["text"],
                )

            def fake_embeddings(indexed_chunks):
                return [
                    IndexedChunkEmbedding(
                        chunk_id=indexed_chunk.chunk.chunk_id,
                        embedding_text=indexed_chunk.embedding_text,
                        model="test-model",
                        dimensions=2,
                        embedding=[1.0, 0.0],
                    )
                    for indexed_chunk in indexed_chunks
                ]

            with patch(
                "conversation_core.rag.build_vector_store."
                "embed_indexed_chunks",
                side_effect=fake_embeddings,
            ):
                indexed_chunks, embeddings = build_vector_store(
                    input_path=input_path,
                    output_path=output_path,
                    document_builder=document_builder,
                )

            self.assertEqual(len(indexed_chunks), 2)
            self.assertEqual(len(embeddings), 2)
            self.assertTrue(
                (output_path / "vector_index.json").exists()
            )
            self.assertTrue(
                (output_path / "vector_embeddings.npy").exists()
            )


if __name__ == "__main__":
    unittest.main()
