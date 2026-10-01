from __future__ import annotations

from conversation_core.services.diagnostic_summary_service import (
    verbose_diagnostics_enabled,
)
from docent.schemas.preference_schemas import (
    DocentPreferenceEvidence,
    DocentPreferenceState,
)
from extensions.retrieval.schemas.chunk_schemas import RetrievedChunk


def build_retrieval_debug_summary(
    *,
    subjects: list[str],
    retrieved_chunks: list[RetrievedChunk],
    subject_retrievals: list[dict],
) -> dict[str, object]:
    summary: dict[str, object] = {
        "used": bool(retrieved_chunks),
        "subjects": list(subjects),
        "chunk_count": len(retrieved_chunks),
        "chunks": [
            {
                "chunk_id": retrieved.chunk.chunk_id,
                "reference": (
                    retrieved.chunk.source_reference
                    or retrieved.chunk.parent_document_id
                ),
                "score": round(float(retrieved.score), 4),
            }
            for retrieved in retrieved_chunks
        ],
        "subject_timings": [
            {
                "subject": retrieval.get("subject"),
                "result_count": retrieval.get("result_count", 0),
                "timings": retrieval.get("timings", {}),
            }
            for retrieval in subject_retrievals
        ],
    }

    if verbose_diagnostics_enabled():
        summary["retrieved_chunks"] = [
            retrieved.model_dump(mode="json")
            for retrieved in retrieved_chunks
        ]
        summary["subject_retrievals"] = subject_retrievals

    return summary


def build_preference_telemetry_summary(
    *,
    before: DocentPreferenceState,
    evidence: DocentPreferenceEvidence,
    after: DocentPreferenceState,
    content_policy: dict,
    analysis: dict,
) -> dict[str, object]:
    policy_used: dict[str, object] = {
        "mode": content_policy.get("mode"),
        "dominant_interest": content_policy.get("dominant_interest"),
    }
    summary: dict[str, object] = {
        "analysis_seconds": analysis.get("analysis_seconds"),
        "preference_state_used": {
            "interests": dict(before.interests),
        },
        "evidence": {
            "interest_signals": [
                signal.model_dump(mode="json")
                for signal in evidence.interest_signals
            ],
        },
        "next_preference_state": {
            "interests": dict(after.interests),
        },
        "policy_used": policy_used,
    }

    if analysis.get("validation_error"):
        summary["validation_error"] = analysis["validation_error"]
        summary["raw_response"] = analysis.get("raw_response")
    elif verbose_diagnostics_enabled():
        summary["analysis"] = analysis
        policy_used["full_policy_debug"] = content_policy

    return summary
