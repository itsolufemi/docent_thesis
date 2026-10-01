from __future__ import annotations

from config import settings
from conversation_core.schemas.query_schemas import QueryResult
from conversation_core.schemas.source_schemas import QuerySource


def verbose_diagnostics_enabled() -> bool:
    return settings.diagnostic_detail == "verbose"


def diagnostic_prompt(prompt: str) -> str | None:
    return prompt if verbose_diagnostics_enabled() else None


def compact_sources(
    sources: list[QuerySource],
) -> list[QuerySource]:
    if verbose_diagnostics_enabled():
        return sources

    identifier_keys = {
        "chunk_id",
        "chunk_ids",
        "document_id",
        "painting_index",
        "discovery_scope",
    }

    return [
        QuerySource(
            source_type=source.source_type,
            title=source.title,
            reference=source.reference,
            url=source.url,
            score=source.score,
            metadata={
                key: value
                for key, value in source.metadata.items()
                if key in identifier_keys
            },
        )
        for source in sources
    ]


def build_query_result_telemetry_summary(
    result: QueryResult,
) -> dict[str, object]:
    debug = result.debug
    summary: dict[str, object] = {
        "response_characters": len(result.response),
        "sources_count": len(result.sources),
        "sources": [
            {
                "reference": source.reference,
                "score": source.score,
            }
            for source in result.sources
        ],
    }

    if debug is not None:
        summary.update(
            {
                "context_source": debug.context_source,
                "retrieval_used": debug.retrieval_used,
                "dialogue_turns_used": debug.dialogue_turns_used,
            }
        )

    return summary
