from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from conversation_core.schemas.context_schemas import QueryDebugInfo
from conversation_core.api.routes_turn_buffer_stream import (
    _discovery_cycle_summary,
    _tool_execution_summary,
)
from conversation_core.schemas.query_schemas import QueryResult
from conversation_core.schemas.source_schemas import QuerySource
from conversation_core.services.diagnostic_summary_service import (
    build_query_result_telemetry_summary,
    compact_sources,
    diagnostic_prompt,
)
from docent.services.docent_diagnostic_service import (
    build_retrieval_debug_summary,
)
from docent.services.docent_query_service import (
    resolve_context_assessment,
)
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalChunk,
    RetrievedChunk,
)


class DiagnosticSummaryServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.diagnostic_summary_service."
        "settings.diagnostic_detail",
        "compact",
    )
    def test_compact_mode_omits_prompt_source_content_and_metadata(self) -> None:
        source = QuerySource(
            source_type="retrieval",
            title="The Swing",
            reference="painting:1",
            score=0.75,
            snippet="A complete evidence passage.",
            metadata={"large": "object", "chunk_id": "chunk-1"},
        )

        self.assertIsNone(diagnostic_prompt("full prompt"))
        compact = compact_sources([source])[0]
        self.assertIsNone(compact.snippet)
        self.assertEqual(compact.metadata, {"chunk_id": "chunk-1"})
        self.assertEqual(compact.reference, "painting:1")
        self.assertEqual(compact.score, 0.75)

    @patch(
        "conversation_core.services.diagnostic_summary_service."
        "settings.diagnostic_detail",
        "verbose",
    )
    def test_verbose_mode_preserves_full_diagnostics(self) -> None:
        source = QuerySource(
            source_type="retrieval",
            snippet="Evidence.",
            metadata={"chunk_id": "chunk-1"},
        )

        self.assertEqual(diagnostic_prompt("full prompt"), "full prompt")
        self.assertIs(compact_sources([source])[0], source)

    @patch(
        "conversation_core.services.diagnostic_summary_service."
        "settings.diagnostic_detail",
        "compact",
    )
    def test_retrieval_summary_keeps_ids_scores_but_not_text(self) -> None:
        retrieved = RetrievedChunk(
            chunk=RetrievalChunk(
                chunk_id="chunk-1",
                chunk_type="description",
                parent_document_id="painting:1",
                source_reference="painting:1",
                text="Full retrieved artwork text.",
            ),
            score=0.81234,
        )

        summary = build_retrieval_debug_summary(
            subjects=["The Swing"],
            retrieved_chunks=[retrieved],
            subject_retrievals=[],
        )

        self.assertEqual(summary["chunk_count"], 1)
        self.assertEqual(summary["chunks"][0]["chunk_id"], "chunk-1")
        self.assertEqual(summary["chunks"][0]["score"], 0.8123)
        self.assertNotIn("retrieved_chunks", summary)
        self.assertNotIn("Full retrieved artwork text.", str(summary))

    def test_turn_telemetry_uses_summary_not_response_prompt_or_timings(self) -> None:
        result = QueryResult(
            request="Tell me about it.",
            response="A substantial answer.",
            sources=[
                QuerySource(
                    source_type="retrieval",
                    reference="painting:1",
                    score=0.8,
                )
            ],
            debug=QueryDebugInfo(
                context_source="direct_routing_tool",
                retrieval_used=True,
                dialogue_turns_used=2,
                prompt="large prompt",
                debug_payload={"timings": {"total_request_seconds": 1.2}},
            ),
        )

        summary = build_query_result_telemetry_summary(result)

        self.assertEqual(summary["response_characters"], 21)
        self.assertEqual(summary["sources_count"], 1)
        self.assertEqual(
            summary["sources"],
            [{"reference": "painting:1", "score": 0.8}],
        )
        self.assertTrue(summary["retrieval_used"])
        self.assertNotIn("response", summary)
        self.assertNotIn("prompt", summary)
        self.assertNotIn("timings", summary)

    def test_tool_telemetry_keeps_exact_call_and_discovery_ranking(self) -> None:
        discovery = {
            "query": "Rococo mythology",
            "scope": "collection",
            "threshold": 0.49,
            "excluded_references": ["painting:118"],
            "raw_candidates": [
                {
                    "rank": 1,
                    "reference": "painting:117",
                    "title": "the rape of europa",
                    "semantic_score": 0.6037,
                    "passed_threshold": True,
                    "selected_rank": 1,
                }
            ],
        }
        summary = _tool_execution_summary(
            tool_name="discover_docent_knowledge",
            arguments={
                "query": "Rococo mythology",
                "scope": "collection",
            },
            result={
                "success": True,
                "message": "Found evidence.",
                "retrieval_used": True,
                "sources": [{}],
                "telemetry": discovery,
            },
        )

        self.assertEqual(summary["tool_name"], "discover_docent_knowledge")
        self.assertEqual(summary["arguments"]["scope"], "collection")
        self.assertEqual(summary["sources_count"], 1)
        self.assertEqual(summary["discovery"], discovery)

    def test_discovery_cycle_telemetry_is_compact_and_response_aware(
        self,
    ) -> None:
        summary = _discovery_cycle_summary(
            arguments={
                "query": "disguising violence through elegance",
                "scope": "collection",
            },
            result={
                "data": {
                    "candidates": [
                        {
                            "reference": "painting:117",
                            "title": "The Rape of Europa",
                            "semantic_score": 0.6037,
                            "evidence": [{"text": "Large evidence text."}],
                        }
                    ]
                }
            },
            primary_text_to_call_seconds=0.04,
            tool_call_to_result_seconds=0.31,
        )

        self.assertTrue(summary["discovery_called"])
        self.assertEqual(summary["scope"], "collection")
        self.assertFalse(summary["continuation_generated"])
        self.assertEqual(
            summary["candidates_returned"],
            [
                {
                    "reference": "painting:117",
                    "title": "The Rape of Europa",
                    "semantic_score": 0.6037,
                }
            ],
        )
        self.assertNotIn("evidence", str(summary))

    @patch(
        "docent.services.docent_query_service.verbose_diagnostics_enabled",
        return_value=False,
    )
    @patch(
        "docent.services.docent_query_service.generate_llm_response",
        return_value=(
            '{"is_relevant":true,"route_type":"response_request",'
            '"requires_retrieval":false,"subjects":[]}'
        ),
    )
    def test_successful_context_parse_omits_raw_response(
        self,
        _generate,
        _verbose,
    ) -> None:
        _, debug = resolve_context_assessment([], "Hello")

        self.assertNotIn("context_resolution_raw", debug)
        self.assertNotIn("context_resolution_validation_error", debug)

    @patch(
        "docent.services.docent_query_service.generate_llm_response",
        return_value="not json",
    )
    def test_failed_context_parse_retains_raw_response(self, _generate) -> None:
        _, debug = resolve_context_assessment([], "Hello")

        self.assertEqual(debug["context_resolution_raw"], "not json")
        self.assertIn("context_resolution_validation_error", debug)


if __name__ == "__main__":
    unittest.main()
