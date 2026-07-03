from typing import Literal

from pydantic import BaseModel, Field


SourceType = Literal[
    "artwork_context",
    "retrieved_artwork",
    "evidence_chunk",
]


class QuerySource(BaseModel):
    source_type: SourceType

    painting_index: int
    title: str
    artist: str | None = None
    inventory_number: str | None = None
    url: str | None = None

    chunk_id: str | None = None
    chunk_type: str | None = None

    matched_fields: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)

    score: int | None = None
    snippet: str | None = None