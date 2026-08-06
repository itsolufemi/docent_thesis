import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.schemas.context_resolution_schemas import (  # noqa: E402
    ContextResolutionAssessment,
)
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    DialogueTurn,
)
from docent.services.docent_query_service import (  # noqa: E402
    _clean_subjects,
    _extract_json_object,
    _retrieve_subjects,
    docent_build_context_resolved_prompt,
    docent_resolve_context,
    resolve_context_assessment,
)


def make_retrieved_chunk(
    chunk_id: str,
    score: float,
    *,
    reference: str,
):
    return SimpleNamespace(
        score=score,
        chunk=SimpleNamespace(
            chunk_id=chunk_id,
            source_reference=reference,
            parent_document_id=reference,
        ),
    )


def make_retrieval_result(results):
    timings = Mock()
    timings.model_dump.return_value = {
        "total_seconds": 0.01,
    }
    return SimpleNamespace(
        results=results,
        timings=timings,
    )


class ContextResolutionSchemaTest(unittest.TestCase):
    def test_schema_accepts_only_the_four_runtime_fields(self) -> None:
        assessment = ContextResolutionAssessment(
            is_relevant=True,
            route_type="response_request",
            requires_retrieval=True,
            subjects=["The Arab Tent"],
        )

        self.assertEqual(
            assessment.model_dump(mode="json"),
            {
                "is_relevant": True,
                "route_type": "response_request",
                "requires_retrieval": True,
                "subjects": ["The Arab Tent"],
            },
        )

    def test_schema_rejects_removed_reference_and_confidence_fields(self) -> None:
        with self.assertRaises(Exception):
            ContextResolutionAssessment.model_validate(
                {
                    "is_relevant": True,
                    "route_type": "response_request",
                    "requires_retrieval": True,
                    "subjects": ["The Arab Tent"],
                    "references": ["painting:581"],
                    "confidence": 0.99,
                }
            )


class ContextResolutionParsingTest(unittest.TestCase):
    def test_subjects_are_trimmed_and_deduplicated_case_insensitively(
        self,
    ) -> None:
        self.assertEqual(
            _clean_subjects(
                [
                    " The Arab Tent ",
                    "the arab tent",
                    "The Rising of the Sun",
                    "",
                ]
            ),
            [
                "The Arab Tent",
                "The Rising of the Sun",
            ],
        )

    def test_json_object_is_extracted_from_markdown_fence(self) -> None:
        payload = {
            "is_relevant": True,
            "route_type": "response_request",
            "requires_retrieval": False,
            "subjects": [],
        }
        text = "```json\n" + json.dumps(payload) + "\n```"

        self.assertEqual(
            json.loads(_extract_json_object(text)),
            payload,
        )

    @patch(
        "docent.services.docent_query_service."
        "generate_llm_response"
    )
    def test_resolver_uses_dialogue_history_and_returns_multiple_subjects(
        self,
        generate_response,
    ) -> None:
        generate_response.return_value = json.dumps(
            {
                "is_relevant": True,
                "route_type": "response_request",
                "requires_retrieval": True,
                "subjects": [
                    "The Arab Tent",
                    "The Rising of the Sun",
                ],
            }
        )
        history = [
            DialogueTurn(
                role="user",
                content="Tell me about The Arab Tent.",
                subjects=["The Arab Tent"],
            ),
            DialogueTurn(
                role="assistant",
                content="It is a nineteenth-century painting.",
                subjects=["The Arab Tent"],
            ),
        ]

        assessment, debug = resolve_context_assessment(
            dialogue_history=history,
            user_input=(
                "Compare it with The Rising of the Sun."
            ),
        )

        self.assertEqual(
            assessment.subjects,
            [
                "The Arab Tent",
                "The Rising of the Sun",
            ],
        )
        self.assertTrue(assessment.requires_retrieval)
        self.assertIsNone(
            debug["context_resolution_validation_error"]
        )

        prompt = generate_response.call_args.kwargs["prompt"]
        self.assertIn(
            "Subjects: ['The Arab Tent']",
            prompt,
        )
        self.assertIn(
            "Compare it with The Rising of the Sun.",
            prompt,
        )

    @patch(
        "docent.services.docent_query_service."
        "generate_llm_response",
        return_value="not valid json",
    )
    def test_invalid_model_output_uses_raw_utterance_fail_safe(
        self,
        _generate_response,
    ) -> None:
        assessment, debug = resolve_context_assessment(
            dialogue_history=[],
            user_input="Tell me about The Swing.",
        )

        self.assertTrue(assessment.is_relevant)
        self.assertEqual(
            assessment.route_type,
            "response_request",
        )
        self.assertTrue(assessment.requires_retrieval)
        self.assertEqual(
            assessment.subjects,
            ["Tell me about The Swing."],
        )
        self.assertIsNotNone(
            debug["context_resolution_validation_error"]
        )


class SubjectRetrievalTest(unittest.TestCase):
    @patch(
        "docent.services.docent_query_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_retrieval_runs_once_for_each_subject_and_deduplicates_chunks(
        self,
        retrieve_chunks,
    ) -> None:
        duplicate = make_retrieved_chunk(
            "chunk:shared",
            0.80,
            reference="painting:581",
        )
        retrieve_chunks.side_effect = [
            make_retrieval_result(
                [
                    make_retrieved_chunk(
                        "chunk:arab",
                        0.91,
                        reference="painting:581",
                    ),
                    duplicate,
                ]
            ),
            make_retrieval_result(
                [
                    duplicate,
                    make_retrieved_chunk(
                        "chunk:rising",
                        0.95,
                        reference="painting:118",
                    ),
                ]
            ),
        ]

        merged, debug = _retrieve_subjects(
            [
                "The Arab Tent",
                "The Rising of the Sun",
            ],
            per_subject_limit=3,
            merged_limit=10,
        )

        self.assertEqual(retrieve_chunks.call_count, 2)
        self.assertEqual(
            [
                call.kwargs["query"]
                for call in retrieve_chunks.call_args_list
            ],
            [
                "The Arab Tent",
                "The Rising of the Sun",
            ],
        )
        self.assertEqual(
            [item.chunk.chunk_id for item in merged],
            [
                "chunk:rising",
                "chunk:arab",
                "chunk:shared",
            ],
        )
        self.assertEqual(len(debug), 2)
        self.assertEqual(
            debug[1]["accepted_chunk_ids"],
            ["chunk:rising"],
        )

    @patch(
        "docent.services.docent_query_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_merged_retrieval_respects_total_limit(
        self,
        retrieve_chunks,
    ) -> None:
        retrieve_chunks.return_value = make_retrieval_result(
            [
                make_retrieved_chunk(
                    f"chunk:{index}",
                    float(index),
                    reference=f"painting:{index}",
                )
                for index in range(6)
            ]
        )

        merged, _ = _retrieve_subjects(
            ["Victorian paintings"],
            merged_limit=3,
        )

        self.assertEqual(
            [item.chunk.chunk_id for item in merged],
            ["chunk:5", "chunk:4", "chunk:3"],
        )


class DocentContextResolverTest(unittest.TestCase):
    @patch(
        "docent.services.docent_query_service."
        "build_sources_from_retrieved_chunks",
        return_value=[],
    )
    @patch(
        "docent.services.docent_query_service."
        "_retrieve_subjects"
    )
    @patch(
        "docent.services.docent_query_service."
        "resolve_context_assessment"
    )
    def test_requires_retrieval_runs_subject_retrieval(
        self,
        resolve_assessment,
        retrieve_subjects,
        _build_sources,
    ) -> None:
        assessment = ContextResolutionAssessment(
            is_relevant=True,
            route_type="response_request",
            requires_retrieval=True,
            subjects=[
                "The Arab Tent",
                "The Rising of the Sun",
            ],
        )
        resolve_assessment.return_value = (
            assessment,
            {"context_resolution": assessment.model_dump()},
        )
        chunks = [
            make_retrieved_chunk(
                "chunk:arab",
                0.9,
                reference="painting:581",
            )
        ]
        retrieve_subjects.return_value = (
            chunks,
            [{"subject": "The Arab Tent"}],
        )

        resolved = docent_resolve_context(
            dialogue_history=[],
            user_input="Compare the paintings.",
        )

        retrieve_subjects.assert_called_once_with(
            [
                "The Arab Tent",
                "The Rising of the Sun",
            ]
        )
        self.assertEqual(
            resolved.context_source,
            "subject_vector_retrieval",
        )
        self.assertEqual(
            resolved.prompt_payload["subjects"],
            [
                "The Arab Tent",
                "The Rising of the Sun",
            ],
        )
        self.assertEqual(
            resolved.debug_payload["retrieved_chunk_count"],
            1,
        )

    @patch(
        "docent.services.docent_query_service."
        "build_sources_from_retrieved_chunks",
        return_value=[],
    )
    @patch(
        "docent.services.docent_query_service."
        "_retrieve_subjects"
    )
    @patch(
        "docent.services.docent_query_service."
        "resolve_context_assessment"
    )
    def test_requires_retrieval_false_skips_retrieval_but_keeps_subjects(
        self,
        resolve_assessment,
        retrieve_subjects,
        _build_sources,
    ) -> None:
        assessment = ContextResolutionAssessment(
            is_relevant=True,
            route_type="response_request",
            requires_retrieval=False,
            subjects=["The Arab Tent"],
        )
        resolve_assessment.return_value = (
            assessment,
            {"context_resolution": assessment.model_dump()},
        )

        resolved = docent_resolve_context(
            dialogue_history=[],
            user_input="I understand what you mean.",
        )

        retrieve_subjects.assert_not_called()
        self.assertEqual(
            resolved.context_source,
            "no_external_context",
        )
        self.assertEqual(
            resolved.prompt_payload["subjects"],
            ["The Arab Tent"],
        )
        self.assertEqual(
            resolved.debug_payload["subject_retrievals"],
            [],
        )

    def test_response_prompt_contains_original_utterance_and_resolution(
        self,
    ) -> None:
        resolved = SimpleNamespace(
            prompt_payload={
                "context_resolution": {
                    "is_relevant": True,
                    "route_type": "response_request",
                    "requires_retrieval": True,
                    "subjects": ["The Arab Tent"],
                },
                "artwork": None,
                "retrieved_documents": [],
                "retrieved_chunks": [],
            }
        )

        prompt = docent_build_context_resolved_prompt(
            user_input="Why does it look theatrical?",
            dialogue_history=[],
            resolved_context=resolved,
        )

        self.assertIn(
            "ORIGINAL VISITOR UTTERANCE\nWhy does it look theatrical?",
            prompt,
        )
        self.assertIn(
            "subjects: ['The Arab Tent']",
            prompt,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
