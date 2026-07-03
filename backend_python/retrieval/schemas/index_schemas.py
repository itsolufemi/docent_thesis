from pydantic import BaseModel, Field

from backend_python.retrieval.schemas.rag_schemas import EvidenceChunk


class IndexedEvidenceChunk(BaseModel):
    chunk: EvidenceChunk
    embedding_text: str
    metadata: dict[str, str | int | None] = Field(default_factory=dict)


class RagIndexResponse(BaseModel):
    chunks: list[IndexedEvidenceChunk]


class RagIndexSummaryResponse(BaseModel):
    total_chunks: int
    chunk_types: dict[str, int]
    artworks_indexed: int