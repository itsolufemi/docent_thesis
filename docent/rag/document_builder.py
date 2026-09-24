from __future__ import annotations

from typing import Any

from docent.services.artwork_service import (
    normalise_artwork_record,
)
from docent.services.docent_retrieval_adapter import (
    artwork_to_retrieval_chunks,
)
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalChunk,
)


def build_artwork_document(
    record: dict[str, Any],
) -> list[RetrievalChunk]:
    """Convert one raw Docent artwork record into retrieval chunks."""
    artwork = normalise_artwork_record(record)
    return artwork_to_retrieval_chunks(artwork)
