from pydantic import BaseModel, Field

from conversation_core.schemas.source_schemas import QuerySource


class QueryDebugInfo(BaseModel):
    conversation_found: bool | None = None
    subject_reference: str | None = None
    context_source: str = "no_context"
    context_used: bool = False
    dialogue_turns_used: int = 0
    prompt: str | None = None

    retrieval_used: bool = False
    sources_count: int = 0
    sources: list[QuerySource] = Field(default_factory=list)

    debug_payload: dict[str, object] = Field(default_factory=dict)