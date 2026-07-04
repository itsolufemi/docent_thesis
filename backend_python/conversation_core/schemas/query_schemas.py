from pydantic import BaseModel, Field

from backend_python.conversation_core.schemas.context_schemas import QueryDebugInfo
from backend_python.conversation_core.schemas.source_schemas import QuerySource


class QueryRequest(BaseModel):
    text: str
    conversation_id: str | None = None
    subject_reference: str | None = None
    debug: bool = False


class QueryResponse(BaseModel):
    request: str
    response: str
    conversation_id: str | None = None
    subject_reference: str | None = None
    sources: list[QuerySource] = Field(default_factory=list)
    debug: QueryDebugInfo | None = None

class QueryResult(BaseModel):
    request: str
    response: str
    conversation_id: str | None = None
    subject_reference: str | None = None
    sources: list[QuerySource] = Field(default_factory=list)
    debug: QueryDebugInfo | None = None

class ResolvedContext(BaseModel):
    context_source: str
    subject_reference: str | None = None
    prompt_payload: dict = Field(default_factory=dict)
    sources: list[QuerySource] = Field(default_factory=list)
    debug_payload: dict = Field(default_factory=dict)

