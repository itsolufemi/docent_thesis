from typing import Literal

from pydantic import BaseModel, Field


EvidenceChunkType = Literal[
    "identity",
    "description",
    "provenance",
    "location",
    "metadata",
]


class EvidenceChunk(BaseModel):
    chunk_id: str
    chunk_type: EvidenceChunkType

    painting_index: int
    title: str
    artist: str | None = None
    inventory_number: str | None = None
    url: str | None = None

    text: str


class RetrievedEvidenceChunk(BaseModel):
    chunk: EvidenceChunk
    score: int
    matched_terms: list[str] = Field(default_factory=list)


class RagSearchResponse(BaseModel):
    query: str
    results: list[RetrievedEvidenceChunk]


class RagChunkListResponse(BaseModel):
    chunks: list[EvidenceChunk]