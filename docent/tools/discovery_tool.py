from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from conversation_core.memory.conversation_store import get_conversation
from conversation_core.schemas.source_schemas import QuerySource
from conversation_core.schemas.tool_schemas import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)
from docent.schemas.discovery_schemas import PreparedDiscoveryState
from docent.services.docent_discovery_service import (
    discover_docent_candidates,
)
from docent.services.docent_discovery_store import (
    docent_discovery_store,
)
from docent.tools.docent_tool_registry import docent_tool_registry


class DocentDiscoveryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    scope: Literal["current_artwork", "collection", "both"]
    reuse_prepared: bool = False


DOCENT_DISCOVERY_TOOL = ToolDefinition(
    name="discover_docent_knowledge",
    description=(
        "Semantically search Wallace Collection knowledge for a potentially "
        "worthwhile discovery connected to the visitor's conversation. Use "
        "scope=current_artwork to investigate an unexplored aspect of the "
        "current work. Use scope=collection to find other artworks meaningfully "
        "connected to a concept, theme, technique, interpretation, period, or "
        "historical context. Use scope=both after a substantive artwork answer "
        "to prepare both an unexplored aspect of the current work and related "
        "works. Set reuse_prepared=true when a later delegated request follows "
        "the direction of an earlier prepared discovery. This is conceptual "
        "semantic discovery, not exact-"
        "title retrieval. Do not mention or tease a possible discovery until "
        "this tool has returned evidence supporting it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "scope": {
                "type": "string",
                "enum": ["current_artwork", "collection", "both"],
            },
            "reuse_prepared": {"type": "boolean", "default": False},
        },
        "required": ["query", "scope"],
        "additionalProperties": False,
    },
)


def _conversation_artwork_references(
    conversation_id: str,
) -> tuple[str | None, set[str]]:
    state = get_conversation(conversation_id)
    if state is None:
        return None, set()

    visited_references: set[str] = set()
    current_reference: str | None = None
    for turn in state.dialogue_history:
        for reference in turn.reference:
            if reference.startswith("painting:"):
                visited_references.add(reference)
                current_reference = reference

    return current_reference, visited_references


def discover_docent_knowledge(
    context: ToolExecutionContext,
    arguments: dict,
) -> ToolExecutionResult:
    validated = DocentDiscoveryArguments.model_validate(arguments)
    current_reference, visited_references = (
        _conversation_artwork_references(context.conversation_id)
    )
    prepared = docent_discovery_store.get(context.conversation_id)
    prepared_reused = bool(
        validated.reuse_prepared
        and prepared is not None
        and prepared.current_reference == current_reference
    )
    if prepared_reused and prepared is not None:
        current_candidates = (
            prepared.current_artwork_candidates
            if validated.scope in {"current_artwork", "both"}
            else []
        )
        collection_candidates = (
            prepared.collection_candidates
            if validated.scope in {"collection", "both"}
            else []
        )
        candidates = (
            current_candidates
            if validated.scope == "current_artwork"
            else collection_candidates
            if validated.scope == "collection"
            else []
        )
        discovery = {
            "query": prepared.query,
            "requested_query": validated.query.strip(),
            "scope": validated.scope,
            "current_reference": current_reference,
            "candidates": candidates,
            "current_artwork_candidates": current_candidates,
            "collection_candidates": collection_candidates,
            "retrieval_performed": False,
            "retrieval_timings": None,
            "prepared_reused": True,
            "telemetry": {
                "query": prepared.query,
                "scope": validated.scope,
                "current_reference": current_reference,
                "excluded_references": sorted(visited_references),
                "allowed_chunk_types": [],
                "threshold": None,
                "retrieval_limit": 0,
                "retrieval_performed": False,
                "raw_candidate_count": 0,
                "raw_candidates": [],
                "selected_candidates": [],
                "retrieval_timings": None,
                "lanes": {},
                "prepared_reused": True,
                "candidates_prepared": {
                    "current_artwork": len(current_candidates),
                    "collection": len(collection_candidates),
                },
            },
        }
    else:
        discovery = discover_docent_candidates(
            query=validated.query.strip(),
            scope=validated.scope,
            current_reference=current_reference,
            excluded_references=(
                visited_references
                if validated.scope in {"collection", "both"}
                else None
            ),
        )
        current_candidates = discovery["current_artwork_candidates"]
        collection_candidates = discovery["collection_candidates"]

    trigger_phase = (
        "post_response"
        if context.visitor_facing_text.strip()
        else "reactive"
    )
    if prepared_reused and prepared is not None:
        docent_discovery_store.set(
            context.conversation_id,
            prepared.model_copy(
                update={
                    "source_response_text": (
                        context.visitor_facing_text.strip()
                    ),
                    "request_id": context.request_id,
                    "discovery_trigger_phase": trigger_phase,
                    "prepared_reused": True,
                },
                deep=True,
            ),
        )
    discovery_telemetry = dict(discovery.get("telemetry") or {})
    discovery_telemetry.update(
        {
            "discovery_trigger_phase": trigger_phase,
            "prepared_reused": prepared_reused,
            "request_id": context.request_id,
            "candidates_prepared": {
                "current_artwork": len(current_candidates),
                "collection": len(collection_candidates),
            },
        }
    )
    model_discovery = {
        key: value
        for key, value in discovery.items()
        if key not in {"telemetry", "candidates", "retrieval_timings"}
    }
    model_discovery["prepared_reused"] = prepared_reused
    candidate_lanes = [
        *((candidate, "current_artwork") for candidate in current_candidates),
        *((candidate, "collection") for candidate in collection_candidates),
    ]
    unique_candidates = {
        candidate["reference"]: (candidate, lane)
        for candidate, lane in candidate_lanes
    }
    sources = [
        QuerySource(
            source_type="discovery_evidence",
            title=candidate["title"],
            reference=candidate["reference"],
            url=(
                candidate["evidence"][0].get("url")
                if candidate["evidence"]
                else None
            ),
            score=candidate["semantic_score"],
            snippet=(
                candidate["evidence"][0]["text"]
                if candidate["evidence"]
                else None
            ),
            metadata={
                "painting_index": candidate["painting_index"],
                "artist": candidate["artist"],
                "room_index": candidate["room_index"],
                "room_name": candidate["room_name"],
                "room_distance": candidate["room_distance"],
                "discovery_scope": lane,
                "chunk_ids": [
                    evidence["chunk_id"]
                    for evidence in candidate["evidence"]
                    if evidence.get("chunk_id")
                ],
            },
        )
        for candidate, lane in unique_candidates.values()
    ]
    retrieval_performed = discovery["retrieval_performed"]

    if not prepared_reused:
        docent_discovery_store.set(
            context.conversation_id,
            PreparedDiscoveryState(
                conversation_id=context.conversation_id,
                query=validated.query.strip(),
                source_response_text=context.visitor_facing_text.strip(),
                current_reference=current_reference,
                current_artwork_candidates=current_candidates,
                collection_candidates=collection_candidates,
                request_id=context.request_id,
                discovery_trigger_phase=trigger_phase,
                prepared_reused=False,
            ),
        )

    return ToolExecutionResult(
        tool_name=DOCENT_DISCOVERY_TOOL.name,
        success=True,
        message=(
            "Found evidence for potential Docent discoveries."
            if unique_candidates
            else "No sufficiently strong discovery evidence was found."
        ),
        retrieval_used=retrieval_performed,
        data=model_discovery,
        dialogue_state=None,
        sources=sources,
        telemetry=discovery_telemetry,
    )


docent_tool_registry.register(
    DOCENT_DISCOVERY_TOOL,
    discover_docent_knowledge,
)
