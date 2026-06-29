from pydantic import BaseModel, Field

from schemas.context_schemas import QueryDebugInfo
from schemas.source_schemas import QuerySource


class QueryRequest(BaseModel):
    text: str
    session_id: str | None = None
    painting_index: int | None = None
    debug: bool = False


class QueryResponse(BaseModel):
    request: str
    response: str
    session_id: str | None = None
    painting_index: int | None = None
    sources: list[QuerySource] = Field(default_factory=list)
    debug: QueryDebugInfo | None = None