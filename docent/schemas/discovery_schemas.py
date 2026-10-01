from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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
    scope: Literal["current_artwork", "collection", "both"]
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
    lanes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    discovery_trigger_phase: Literal["post_response", "reactive"] | None = None
    prepared_reused: bool = False
    request_id: str | None = None
    candidates_prepared: dict[str, int] = Field(default_factory=dict)


class PreparedDiscoveryState(BaseModel):
    conversation_id: str
    query: str
    source_response_text: str = ""
    current_reference: str | None = None
    current_artwork_candidates: list[dict[str, Any]] = Field(
        default_factory=list
    )
    collection_candidates: list[dict[str, Any]] = Field(
        default_factory=list
    )
    surfaced_reference: str | None = None
    discovery_trigger_phase: Literal["post_response", "reactive"] = (
        "reactive"
    )
    prepared_reused: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    request_id: str | None = None
