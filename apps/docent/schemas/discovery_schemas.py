from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DiscoveryRankedCandidate(BaseModel):
    rank: int = Field(ge=1)
    reference: str
    title: str
    semantic_score: float
    passed_threshold: bool
    selected_rank: int | None = Field(default=None, ge=1)


class DiscoveryTelemetry(BaseModel):
    query: str
    scope: Literal["current_artwork", "collection"]
    current_reference: str | None = None
    excluded_references: list[str] = Field(default_factory=list)
    allowed_chunk_types: list[str] = Field(default_factory=list)
    threshold: float
    retrieval_limit: int
    retrieval_performed: bool
    raw_candidate_count: int
    raw_candidates: list[DiscoveryRankedCandidate] = Field(
        default_factory=list
    )
    selected_candidates: list[DiscoveryRankedCandidate] = Field(
        default_factory=list
    )
    retrieval_timings: dict | None = None
