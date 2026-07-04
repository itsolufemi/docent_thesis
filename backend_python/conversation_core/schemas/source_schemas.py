from pydantic import BaseModel, Field


class QuerySource(BaseModel):
    source_type: str
    title: str | None = None
    reference: str | None = None
    url: str | None = None
    score: float | int | None = None
    snippet: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)