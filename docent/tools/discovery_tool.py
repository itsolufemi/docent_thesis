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
from docent.services.docent_discovery_service import (
    discover_docent_candidates,
)
from docent.tools.docent_tool_registry import docent_tool_registry


class DocentDiscoveryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    scope: Literal["current_artwork", "collection"]
    purpose: Literal["proactive", "delegated"] = "proactive"


DOCENT_DISCOVERY_TOOL = ToolDefinition(
    name="discover_docent_knowledge",
    allowed_phases={
        "primary",
        "post_answer",
    },
    description=(
        "Semantically search Wallace Collection knowledge to help move the "
        "conversation into an appropriate new artwork, subject, or idea. Do "
        "not use this tool merely because a related artwork or concept exists. "
        "For proactive discovery, use it only after the primary answer and only "
        "when the conversation has reached a Subject Transition Point. Continue "
        "guiding worthwhile exploration of the current subject instead of "
        "transitioning prematurely. Do not call discovery between ordinary "
        "artwork retrieval and the primary answer. If the visitor explicitly "
        "asks to move on, asks what to see next, requests a recommendation, or "
        "otherwise delegates the choice, it may be called before answering. "
        "Use purpose=delegated only for that explicit delegated case; otherwise "
        "use purpose=proactive. Use "
        "scope=current_artwork to investigate an unexplored aspect of the "
        "current work. Use scope=collection to find other artworks meaningfully "
        "connected to a concept, theme, technique, interpretation, period, or "
        "historical context. This is conceptual semantic discovery, not exact-"
        "title retrieval. Prefer transitions grounded in interests, observations, "
        "questions, or themes that emerged in the dialogue, without claiming "
        "that the visitor likes something merely because it was discussed. Do "
        "not mention or tease a possible discovery until this tool has returned "
        "evidence supporting it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "scope": {
                "type": "string",
                "enum": ["current_artwork", "collection"],
            },
            "purpose": {
                "type": "string",
                "enum": ["proactive", "delegated"],
                "default": "proactive",
            },
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
    if (
        validated.purpose == "proactive"
        and context.response_phase != "post_answer"
    ):
        return ToolExecutionResult(
            tool_name=DOCENT_DISCOVERY_TOOL.name,
            success=False,
            message=(
                "Proactive discovery is only available during "
                "the post-answer discovery phase."
            ),
            retrieval_used=False,
            data={},
            dialogue_state=None,
            sources=[],
        )

    current_reference, visited_references = (
        _conversation_artwork_references(context.conversation_id)
    )
    discovery = discover_docent_candidates(
        query=validated.query.strip(),
        scope=validated.scope,
        current_reference=current_reference,
        excluded_references=(
            visited_references
            if validated.scope == "collection"
            else None
        ),
    )
    discovery_telemetry = dict(discovery.get("telemetry") or {})
    model_discovery = {
        key: value
        for key, value in discovery.items()
        if key != "telemetry"
    }
    candidates = discovery["candidates"]
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
                "discovery_scope": validated.scope,
                "chunk_ids": [
                    evidence["chunk_id"]
                    for evidence in candidate["evidence"]
                    if evidence.get("chunk_id")
                ],
            },
        )
        for candidate in candidates
    ]
    retrieval_performed = discovery["retrieval_performed"]

    return ToolExecutionResult(
        tool_name=DOCENT_DISCOVERY_TOOL.name,
        success=True,
        message=(
            "Found evidence for potential Docent discoveries."
            if candidates
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
