from pydantic import BaseModel, Field


class RetrievalDocument(BaseModel):
    document_id: str
    title: str | None = None
    text: str
    source_reference: str | None = None
    url: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievedDocument(BaseModel):
    document: RetrievalDocument
    score: float | int
    matched_terms: list[str] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)
    snippet: str | None = None


class RetrievalSearchResponse(BaseModel):
    query: str
    results: list[RetrievedDocument] = Field(default_factory=list)