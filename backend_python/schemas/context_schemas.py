from typing import Literal

from pydantic import BaseModel, Field

from schemas.rag_schemas import RetrievedEvidenceChunk
from schemas.retrieval_schemas import RetrievedArtwork
from schemas.source_schemas import QuerySource


ContextSource = Literal[
    "direct_painting_index",
    "session_current_painting",
    "no_artwork_context",
    "painting_index_not_found",
    "session_not_found",
    "retrieval_results",
    "retrieval_no_results",
    "rag_evidence_chunks",
    "rag_no_evidence",
]


class QueryDebugInfo(BaseModel):
    resolved_painting_index: int | None = None
    context_source: ContextSource
    artwork_context_used: bool
    dialogue_turns_used: int
    prompt: str | None = None

    retrieval_used: bool = False
    retrieval_results: list[RetrievedArtwork] = Field(default_factory=list)

    rag_used: bool = False
    rag_results: list[RetrievedEvidenceChunk] = Field(default_factory=list)

    sources_count: int = 0
    sources: list[QuerySource] = Field(default_factory=list)