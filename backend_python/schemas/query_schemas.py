from pydantic import BaseModel


class QueryRequest(BaseModel):
    text: str
    session_id: str | None = None
    painting_index: int | None = None


class QueryResponse(BaseModel):
    request: str
    response: str
    session_id: str | None = None
    painting_index: int | None = None