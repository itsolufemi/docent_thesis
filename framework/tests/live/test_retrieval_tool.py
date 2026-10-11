from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FRAMEWORK_ROOT.parent

for import_root in (REPOSITORY_ROOT, FRAMEWORK_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from core_engine.schemas.tool_schemas import (
    ToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
)
from core_engine.tools.retrieval_tool import create_retrieval_tool
from core_engine.tools.tool_registry import ToolRegistry
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalChunk,
    RetrievedChunk,
    VectorRetrievalResult,
)


def retrieved_chunk(
    number: int,
    *,
    score: float,
    metadata: dict[str, object] | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=RetrievalChunk(
            chunk_id=f"chunk:{number}",
            chunk_type="identity",
            parent_document_id=f"document:{number}",
            title=f"Subject {number}",
            text=f"Evidence {number}.",
            source_reference=f"reference:{number}",
            url=f"https://example.test/{number}",
            metadata=metadata or {},
        ),
        score=score,
    )


def execute(
    registry: ToolRegistry,
    *,
    subjects: list[str],
) -> ToolExecutionResult:
    return registry.execute(
        ToolCall(
            name="retrieve_knowledge",
            arguments={"subjects": subjects},
        ),
        ToolExecutionContext(conversation_id="conversation-test"),
    )


class RetrievalToolTest(unittest.TestCase):
    def create_registry(
        self,
        retriever,
        *,
        max_results: int = 10,
    ) -> tuple[ToolRegistry, ToolDefinition]:
        definition, handler = create_retrieval_tool(
            retriever,
            max_results=max_results,
        )
        registry = ToolRegistry()
        registry.register(definition, handler)
        return registry, definition

    def test_single_subject_returns_evidence(self) -> None:
        retriever = Mock(
            return_value=VectorRetrievalResult(
                results=[retrieved_chunk(1, score=0.9)]
            )
        )
        registry, _ = self.create_registry(retriever)

        result = execute(registry, subjects=["The Swing"])

        self.assertTrue(result.success)
        self.assertTrue(result.retrieval_used)
        self.assertEqual(result.tool_name, "retrieve_knowledge")
        self.assertEqual(result.message, "Retrieved relevant knowledge.")
        self.assertEqual(len(result.data["evidence"]), 1)
        self.assertEqual(
            result.dialogue_state.references,
            ["reference:1"],
        )
        retriever.assert_called_once_with("The Swing")

    def test_multiple_subjects_call_provider_for_each_subject(self) -> None:
        retriever = Mock(
            side_effect=[
                VectorRetrievalResult(
                    results=[retrieved_chunk(1, score=0.9)]
                ),
                VectorRetrievalResult(
                    results=[retrieved_chunk(2, score=0.8)]
                ),
            ]
        )
        registry, _ = self.create_registry(retriever)

        result = execute(registry, subjects=["First", "Second"])

        self.assertEqual(
            retriever.call_args_list,
            [call("First"), call("Second")],
        )
        self.assertEqual(
            result.dialogue_state.subjects,
            ["First", "Second"],
        )

    def test_duplicate_chunks_are_returned_once(self) -> None:
        shared = retrieved_chunk(1, score=0.9)
        retriever = Mock(
            side_effect=[
                VectorRetrievalResult(results=[shared]),
                VectorRetrievalResult(
                    results=[shared, retrieved_chunk(2, score=0.8)]
                ),
            ]
        )
        registry, _ = self.create_registry(retriever)

        result = execute(registry, subjects=["First", "Second"])

        self.assertEqual(len(result.data["evidence"]), 2)
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(
            [source.metadata["chunk_id"] for source in result.sources],
            ["chunk:1", "chunk:2"],
        )

    def test_results_are_ranked_before_limit_is_applied(self) -> None:
        retriever = Mock(
            return_value=VectorRetrievalResult(
                results=[
                    retrieved_chunk(1, score=0.1),
                    retrieved_chunk(2, score=0.9),
                    retrieved_chunk(3, score=0.5),
                ]
            )
        )
        registry, _ = self.create_registry(retriever, max_results=2)

        result = execute(registry, subjects=["Rank these"])

        self.assertEqual(
            [item["score"] for item in result.data["evidence"]],
            [0.9, 0.5],
        )
        self.assertEqual(
            result.dialogue_state.references,
            ["reference:2", "reference:3"],
        )

    def test_empty_retrieval_is_a_successful_retrieval(self) -> None:
        registry, _ = self.create_registry(
            Mock(return_value=VectorRetrievalResult(results=[]))
        )

        result = execute(registry, subjects=["Unknown"])

        self.assertTrue(result.success)
        self.assertTrue(result.retrieval_used)
        self.assertEqual(result.data["evidence"], [])
        self.assertEqual(result.sources, [])
        self.assertEqual(result.dialogue_state.references, [])

    def test_invalid_arguments_keep_registry_validation_behaviour(self) -> None:
        registry, _ = self.create_registry(Mock())

        result = execute(registry, subjects=[])

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "The tool arguments were invalid.",
        )
        self.assertIn("validation_errors", result.data)

    def test_source_metadata_is_preserved(self) -> None:
        registry, _ = self.create_registry(
            Mock(
                return_value=VectorRetrievalResult(
                    results=[
                        retrieved_chunk(
                            1,
                            score=0.9,
                            metadata={
                                "image_reference": "images/1.jpg",
                                "room": "Gallery One",
                            },
                        )
                    ]
                )
            )
        )

        result = execute(registry, subjects=["Metadata"])

        source = result.sources[0]
        self.assertEqual(source.metadata["image_reference"], "images/1.jpg")
        self.assertEqual(source.metadata["room"], "Gallery One")
        self.assertEqual(source.metadata["chunk_id"], "chunk:1")
        self.assertEqual(source.metadata["chunk_type"], "identity")

    def test_registration_exposes_generic_tool_name(self) -> None:
        registry, definition = self.create_registry(Mock())

        self.assertEqual(definition.name, "retrieve_knowledge")
        self.assertTrue(registry.has_tool("retrieve_knowledge"))
        self.assertFalse(registry.has_tool("retrieve_docent_knowledge"))

    def test_invalid_max_results_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_results"):
            create_retrieval_tool(Mock(), max_results=0)


class DocentRetrievalConfigurationTest(unittest.TestCase):
    @patch(
        "apps.docent.tools.retrieval_tool."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_docent_registry_uses_existing_retrieval_tuning(
        self,
        retrieve,
    ) -> None:
        from apps.docent.tools import docent_tool_registry

        retrieve.return_value = VectorRetrievalResult(results=[])

        result = docent_tool_registry.execute(
            ToolCall(
                name="retrieve_knowledge",
                arguments={"subjects": ["Queen Victoria"]},
            ),
            ToolExecutionContext(conversation_id="docent-test"),
        )

        self.assertTrue(result.success)
        retrieve.assert_called_once_with(
            query="Queen Victoria",
            limit=4,
            expand_parent_documents=True,
            use_hybrid_scoring=True,
            apply_confidence_gate=True,
            min_confidence_score=0.45,
        )
        self.assertTrue(docent_tool_registry.has_tool("retrieve_knowledge"))
        self.assertTrue(
            docent_tool_registry.has_tool("discover_docent_knowledge")
        )
        definition = next(
            item
            for item in docent_tool_registry.get_definitions()
            if item.name == "retrieve_knowledge"
        )
        subjects_description = definition.parameters[
            "properties"
        ]["subjects"]["description"]
        self.assertIn("artwork, artist, concept", subjects_description)
        self.assertIn("Do not invent a second subject", subjects_description)


if __name__ == "__main__":
    unittest.main()
