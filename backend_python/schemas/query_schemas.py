from pydantic import BaseModel

from schemas.context_schemas import QueryDebugInfo


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
    debug: QueryDebugInfo | None = None