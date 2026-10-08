from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    text: str


class EmbeddingResponse(BaseModel):
    text: str
    model: str
    dimensions: int
    embedding: list[float] = Field(default_factory=list)


class IndexedChunkEmbedding(BaseModel):
    chunk_id: str
    embedding_text: str
    model: str
    dimensions: int
    embedding: list[float] = Field(default_factory=list)


class EmbeddingIndexResponse(BaseModel):
    chunks: list[IndexedChunkEmbedding] = Field(default_factory=list)


class EmbeddingIndexSummaryResponse(BaseModel):
    total_vectors: int
    dimensions: int
    model: str