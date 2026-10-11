from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core_engine.schemas.source_schemas import QuerySource
from core_engine.schemas.tool_schemas import (
    ToolDefinition,
    ToolDialogueStateUpdate,
    ToolExecutionContext,
    ToolExecutionResult,
)
from core_engine.tools.tool_registry import ToolHandler
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievedChunk,
    VectorRetrievalResult,
)


RetrievalProvider = Callable[[str], VectorRetrievalResult]


class RetrievalArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str] = Field(min_length=1)


DEFAULT_RETRIEVAL_DESCRIPTION = (
    "Retrieve knowledge needed to answer the user. Identify every independent "
    "subject whose knowledge is currently needed and include all subjects "
    "already known in one call. When retrieval returns useful knowledge for "
    "a subject, use that result rather than repeatedly reformulating the same "
    "information need. Retrieve again only for a distinct subject or when the "
    "previous result did not provide enough information to answer."
)
DEFAULT_SUBJECTS_DESCRIPTION = (
    "All currently known subjects whose knowledge is needed for this response. "
    "Include multiple independent subjects in the same call when they are "
    "already known. Do not invent another subject merely to fill the list."
)


def _retrieval_parameters(
    subjects_description: str,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "subjects": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "minItems": 1,
                "description": subjects_description,
            },
        },
        "required": ["subjects"],
        "additionalProperties": False,
    }


def _reference_for(result: RetrievedChunk) -> str:
    return (
        result.chunk.source_reference
        or result.chunk.parent_document_id
    )


def create_retrieval_tool(
    retriever: RetrievalProvider,
    *,
    name: str = "retrieve_knowledge",
    description: str | None = None,
    subjects_description: str | None = None,
    max_results: int = 10,
) -> tuple[ToolDefinition, ToolHandler]:
    """Create a provider-neutral, batched retrieval tool."""
    if max_results < 1:
        raise ValueError("max_results must be at least 1.")

    definition = ToolDefinition(
        name=name,
        allowed_phases={"primary"},
        description=description or DEFAULT_RETRIEVAL_DESCRIPTION,
        parameters=_retrieval_parameters(
            subjects_description or DEFAULT_SUBJECTS_DESCRIPTION
        ),
    )

    def retrieve_knowledge(
        context: ToolExecutionContext,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        del context

        validated = RetrievalArguments.model_validate(arguments)
        subjects = validated.subjects
        merged_results: list[RetrievedChunk] = []
        seen_chunk_ids: set[str] = set()

        for subject in subjects:
            result = retriever(subject)

            for retrieved in result.results:
                chunk_id = retrieved.chunk.chunk_id

                if chunk_id in seen_chunk_ids:
                    continue

                seen_chunk_ids.add(chunk_id)
                merged_results.append(retrieved)

        merged_results.sort(
            key=lambda item: float(item.score),
            reverse=True,
        )
        selected_results = merged_results[:max_results]
        references: list[str] = []

        for item in selected_results:
            reference = _reference_for(item)

            if reference and reference not in references:
                references.append(reference)

        evidence = [
            {
                "title": item.chunk.title,
                "reference": _reference_for(item),
                "text": item.chunk.text,
                "score": item.score,
                **(
                    {"image_reference": item.chunk.metadata["image_reference"]}
                    if isinstance(item.chunk.metadata.get("image_reference"), str)
                    and item.chunk.metadata["image_reference"]
                    else {}
                ),
            }
            for item in selected_results
        ]
        sources = [
            QuerySource(
                source_type="retrieved_chunk",
                title=item.chunk.title,
                reference=_reference_for(item),
                url=item.chunk.url,
                score=item.score,
                snippet=item.chunk.text,
                metadata={
                    **item.chunk.metadata,
                    "chunk_id": item.chunk.chunk_id,
                    "chunk_type": item.chunk.chunk_type,
                },
            )
            for item in selected_results
        ]

        return ToolExecutionResult(
            tool_name=definition.name,
            success=True,
            message="Retrieved relevant knowledge.",
            retrieval_used=True,
            data={
                "evidence": evidence,
            },
            dialogue_state=ToolDialogueStateUpdate(
                subjects=subjects,
                references=references,
            ),
            sources=sources,
        )

    return definition, retrieve_knowledge
