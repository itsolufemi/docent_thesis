from pydantic import BaseModel, Field

from schemas.artwork_schemas import Artwork

class RetrievedArtwork(BaseModel):
    artwork: Artwork
    score: int
    matched_fields: list[str] = Field(default_factory=list)
    snippet: str | None = None

class RetrievalSearchResponse(BaseModel):
    query: str
    results: list[RetrievedArtwork]
    