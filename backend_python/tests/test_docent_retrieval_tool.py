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


class DocentRetrievalToolTest(unittest.TestCase):
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
