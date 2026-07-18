from pydantic import BaseModel, Field


class RetrievalChunk(BaseModel):
    chunk_id: str
    chunk_type: str
    parent_document_id: str
    text: str

    title: str | None = None
    source_reference: str | None = None
    url: str | None = None

    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: RetrievalChunk
    score: float | int

    matched_terms: list[str] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)

    snippet: str | None = None


class RetrievalTimings(BaseModel):
    total_seconds: float = 0.0
    query_embedding_seconds: float = 0.0
    vector_index_seconds: float = 0.0
    vector_similarity_seconds: float = 0.0
    parent_expansion_seconds: float = 0.0
    hybrid_reranking_seconds: float = 0.0
    confidence_filter_seconds: float = 0.0
    vector_index_rebuilt: bool = False


class VectorRetrievalResult(BaseModel):
    results: list[RetrievedChunk] = Field(default_factory=list)
    timings: RetrievalTimings = Field(default_factory=RetrievalTimings)


class ChunkSearchResponse(BaseModel):
    query: str
    results: list[RetrievedChunk] = Field(default_factory=list)
    timings: RetrievalTimings | None = None


class ChunkListResponse(BaseModel):
    chunks: list[RetrievalChunk] = Field(default_factory=list)
