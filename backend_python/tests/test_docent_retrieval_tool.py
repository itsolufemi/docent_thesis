from __future__ import annotations

import sys
import unittest

from pathlib import Path
from unittest.mock import call, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from extensions.retrieval.schemas.chunk_schemas import (  # noqa: E402
    RetrievalChunk,
    RetrievedChunk,
    VectorRetrievalResult,
)
from conversation_core.schemas.tool_schemas import (  # noqa: E402
    ToolCall,
    ToolExecutionContext,
)
from docent.tools import (  # noqa: E402
    docent_tool_registry,
)
from docent.tools.retrieval_tool import (  # noqa: E402
    DOCENT_RETRIEVAL_TOOL,
)


class DocentRetrievalToolTest(unittest.TestCase):
    def test_tool_contract_encourages_batched_sufficient_retrieval(
        self,
    ) -> None:
        description = DOCENT_RETRIEVAL_TOOL.description
        subjects_schema = (
            DOCENT_RETRIEVAL_TOOL.parameters[
                "properties"
            ]["subjects"]
        )

        self.assertIn(
            "include all subjects already known in one call",
            description,
        )
        self.assertIn(
            "useful knowledge for a subject",
            description,
        )
        self.assertIn(
            "another distinct subject",
            description,
        )
        self.assertIn(
            "did not provide enough information",
            description,
        )
        self.assertIn(
            "subjects=['The Swing', 'The Rape of Europa']",
            description,
        )
        self.assertIn(
            "subjects=['p487 Wallace Collection']",
            description,
        )
        self.assertEqual(
            subjects_schema["type"],
            "array",
        )
        self.assertEqual(
            subjects_schema["minItems"],
            1,
        )
        self.assertIn(
            "multiple independent subjects",
            subjects_schema["description"],
        )
        self.assertIn(
            "Do not invent a second subject",
            subjects_schema["description"],
        )

    @patch(
        "docent.tools.retrieval_tool."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_retrieves_each_subject_and_deduplicates_chunks(
        self,
        retrieve,
    ) -> None:
        shared = RetrievedChunk(
            chunk=RetrievalChunk(
                chunk_id="painting:1:identity",
                chunk_type="identity",
                parent_document_id="painting:1",
                title="The Swing",
                text="The Swing evidence.",
                source_reference="painting:1",
            ),
            score=0.9,
        )
        second = RetrievedChunk(
            chunk=RetrievalChunk(
                chunk_id="painting:2:identity",
                chunk_type="identity",
                parent_document_id="painting:2",
                title="The Arab Tent",
                text="The Arab Tent evidence.",
                source_reference="painting:2",
            ),
            score=0.8,
        )
        retrieve.side_effect = [
            VectorRetrievalResult(results=[shared]),
            VectorRetrievalResult(results=[shared, second]),
        ]

        result = docent_tool_registry.execute(
            tool_call=ToolCall(
                name="retrieve_docent_knowledge",
                arguments={
                    "subjects": [
                        "The Swing",
                        "The Arab Tent",
                    ]
                },
            ),
            context=ToolExecutionContext(
                conversation_id="conversation-a"
            ),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.retrieval_used)
        self.assertEqual(
            retrieve.call_args_list,
            [
                call(
                    query="The Swing",
                    limit=4,
                    expand_parent_documents=True,
                    use_hybrid_scoring=True,
                    apply_confidence_gate=True,
                    min_confidence_score=0.45,
                ),
                call(
                    query="The Arab Tent",
                    limit=4,
                    expand_parent_documents=True,
                    use_hybrid_scoring=True,
                    apply_confidence_gate=True,
                    min_confidence_score=0.45,
                ),
            ],
        )
        self.assertEqual(
            result.dialogue_state.subjects,
            ["The Swing", "The Arab Tent"],
        )
        self.assertEqual(
            result.dialogue_state.references,
            ["painting:1", "painting:2"],
        )
        self.assertEqual(len(result.data["evidence"]), 2)
        self.assertEqual(len(result.sources), 2)

    @patch(
        "docent.tools.retrieval_tool."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_globally_ranks_before_truncating_and_deriving_references(
        self,
        retrieve,
    ) -> None:
        result_sets = []

        for subject_index in range(3):
            results = []

            for result_index in range(4):
                item_number = subject_index * 4 + result_index + 1
                results.append(
                    RetrievedChunk(
                        chunk=RetrievalChunk(
                            chunk_id=f"chunk:{item_number}",
                            chunk_type="identity",
                            parent_document_id=f"painting:{item_number}",
                            title=f"Artwork {item_number}",
                            text=f"Evidence {item_number}.",
                            source_reference=f"painting:{item_number}",
                        ),
                        score=item_number / 100,
                    )
                )

            result_sets.append(
                VectorRetrievalResult(results=results)
            )

        retrieve.side_effect = result_sets

        result = docent_tool_registry.execute(
            tool_call=ToolCall(
                name="retrieve_docent_knowledge",
                arguments={
                    "subjects": ["First", "Second", "Third"],
                },
            ),
            context=ToolExecutionContext(
                conversation_id="conversation-ranking"
            ),
        )

        evidence_scores = [
            item["score"]
            for item in result.data["evidence"]
        ]
        self.assertEqual(
            evidence_scores,
            [value / 100 for value in range(12, 2, -1)],
        )
        self.assertEqual(
            result.dialogue_state.references,
            [
                f"painting:{value}"
                for value in range(12, 2, -1)
            ],
        )
        self.assertNotIn(
            "painting:1",
            result.dialogue_state.references,
        )
        self.assertNotIn(
            "painting:2",
            result.dialogue_state.references,
        )

    @patch(
        "docent.tools.retrieval_tool."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_empty_retrieval_still_reports_retrieval_used(
        self,
        retrieve,
    ) -> None:
        retrieve.return_value = VectorRetrievalResult(results=[])

        result = docent_tool_registry.execute(
            tool_call=ToolCall(
                name="retrieve_docent_knowledge",
                arguments={"subjects": ["Unknown artwork"]},
            ),
            context=ToolExecutionContext(
                conversation_id="conversation-empty"
            ),
        )

        self.assertTrue(result.success)
        self.assertTrue(result.retrieval_used)
        self.assertEqual(result.sources, [])
        self.assertEqual(result.data["evidence"], [])
        self.assertEqual(
            result.dialogue_state.references,
            [],
        )

    def test_rejects_empty_subjects(self) -> None:
        result = docent_tool_registry.execute(
            tool_call=ToolCall(
                name="retrieve_docent_knowledge",
                arguments={"subjects": []},
            ),
            context=ToolExecutionContext(
                conversation_id="conversation-b"
            ),
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "The tool arguments were invalid.",
        )


if __name__ == "__main__":
    unittest.main()
