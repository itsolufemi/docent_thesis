from __future__ import annotations

import sys
import unittest

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from docent.rag.document_builder import (
    build_artwork_document,
)


class DocentVectorStoreTest(unittest.TestCase):
    def test_artwork_record_preserves_expected_chunks(self) -> None:
        chunks = build_artwork_document(
            {
                "painting_index": 42,
                "title": "Example Portrait",
                "artist": "Example Artist",
                "date": "1900",
                "object_type": "Painting",
                "medium": "Oil on canvas",
                "room_name": "Room 1",
                "description": "A descriptive passage.",
                "provenance": "An ownership history.",
                "inventory_number": "INV-42",
            }
        )

        chunks_by_type = {
            chunk.chunk_type: chunk
            for chunk in chunks
        }

        self.assertEqual(
            set(chunks_by_type),
            {
                "identity",
                "description",
                "provenance",
                "location",
                "metadata",
            },
        )
        self.assertEqual(
            chunks_by_type["identity"].source_reference,
            "painting:42",
        )
        self.assertEqual(
            chunks_by_type["description"].text,
            "A descriptive passage.",
        )
        self.assertEqual(
            chunks_by_type["metadata"].metadata,
            {
                "painting_index": 42,
                "artist": "Example Artist",
                "inventory_number": "INV-42",
            },
        )


if __name__ == "__main__":
    unittest.main()
