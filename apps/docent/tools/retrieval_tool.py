from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core_engine.schemas.source_schemas import (
    QuerySource,
)
from core_engine.schemas.tool_schemas import (
    ToolDefinition,
    ToolDialogueStateUpdate,
    ToolExecutionContext,
    ToolExecutionResult,
)
from apps.docent.services.docent_vector_retrieval_service import (
    retrieve_docent_chunks_by_vector_similarity,
)
from apps.docent.tools.docent_tool_registry import (
    docent_tool_registry,
)


class DocentRetrievalArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str] = Field(min_length=1)


DOCENT_RETRIEVAL_TOOL = ToolDefinition(
    name="retrieve_docent_knowledge",
    allowed_phases={"primary"},
    description=(
        "Retrieve Wallace Collection knowledge needed to answer the "
        "visitor. Identify every independent subject whose knowledge is "
        "currently needed and include all subjects already known in one "
        "call. When retrieval returns useful knowledge for a subject, use "
        "that result to answer rather than repeatedly reformulating and "
        "retrieving the same information need. Make another retrieval call "
        "only when the visitor's request contains another distinct subject "
        "that still needs knowledge, or when the previous retrieval did not "
        "provide enough information to answer. A subject discovered only "
        "after the first result may therefore be retrieved in a later call. "
        "Preferred example: for 'Compare The Swing and The Rape of Europa', "
        "call once with subjects=['The Swing', 'The Rape of Europa']. Avoid "
        "serial reformulations such as subjects=['p487'] followed by "
        "subjects=['p487 Wallace Collection'] when the first result already "
        "contains useful knowledge for P487."
    ),
    parameters={
        "type": "object",
        "properties": {
            "subjects": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "minItems": 1,
                "description": (
                    "All currently known artwork, artist, concept, or "
                    "collection subjects whose knowledge is needed for this "
                    "response. Include multiple independent subjects in the "
                    "same call when they are already known. Do not invent a "
                    "second subject merely to fill the list."
                ),
            },
        },
        "required": ["subjects"],
        "additionalProperties": False,
    },
)


def retrieve_docent_knowledge(
    context: ToolExecutionContext,
    arguments: dict,
) -> ToolExecutionResult:
    del context

    validated = DocentRetrievalArguments.model_validate(
        arguments
    )
    subjects = validated.subjects

    merged_results = []
    seen_chunk_ids: set[str] = set()

    for subject in subjects:
        result = retrieve_docent_chunks_by_vector_similarity(
            query=subject,
            limit=4,
            expand_parent_documents=True,
            use_hybrid_scoring=True,
            apply_confidence_gate=True,
            min_confidence_score=0.45,
        )

        for retrieved in result.results:
            chunk = retrieved.chunk

            if chunk.chunk_id in seen_chunk_ids:
                continue

            seen_chunk_ids.add(chunk.chunk_id)
            merged_results.append(retrieved)

    merged_results.sort(
        key=lambda item: float(item.score),
        reverse=True,
    )
    selected_results = merged_results[:10]
    references: list[str] = []

    for item in selected_results:
        reference = (
            item.chunk.source_reference
            or item.chunk.parent_document_id
        )

        if reference and reference not in references:
            references.append(reference)

    evidence = [
        {
            "title": item.chunk.title,
            "reference": (
                item.chunk.source_reference
                or item.chunk.parent_document_id
            ),
            "text": item.chunk.text,
            "score": item.score,
        }
        for item in selected_results
    ]
    sources = [
        QuerySource(
            source_type="retrieved_chunk",
            title=item.chunk.title,
            reference=(
                item.chunk.source_reference
                or item.chunk.parent_document_id
            ),
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
        tool_name=DOCENT_RETRIEVAL_TOOL.name,
        success=True,
        message="Retrieved relevant Docent knowledge.",
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


docent_tool_registry.register(
    DOCENT_RETRIEVAL_TOOL,
    retrieve_docent_knowledge,
)
