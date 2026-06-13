from pydantic import BaseModel


class QueryRequest(BaseModel):
    text: str
    painting_index: int | None = None


class QueryResponse(BaseModel):
    request: str
    response: str
    painting_index: int | None = None