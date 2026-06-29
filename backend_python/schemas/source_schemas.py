from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "artwork_context",
    "retrieved_artwork"
]

class QuerySource(BaseModel):
    source_type: SourceType

    painting_index: int
    title: str
    artist: str | None = None
    inventory_number: str | None = None
    url: str | None = None

    matched_fields: list[str] = Field(default_factory=list)
    score: int | None = None
    snippet: str | None = None