from pydantic import BaseModel, Field

from extensions.retrieval.schemas.chunk_schemas import RetrievalChunk


class IndexedRetrievalChunk(BaseModel):
    chunk: RetrievalChunk
    embedding_text: str
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievalIndexResponse(BaseModel):
    chunks: list[IndexedRetrievalChunk]


class RetrievalIndexSummaryResponse(BaseModel):
    total_chunks: int
    chunk_types: dict[str, int]
    documents_indexed: int