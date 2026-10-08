from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from core_engine.memory.conversation_store import (  # noqa: E402
    add_dialogue_turn,
    conversations,
    create_conversation,
)
from core_engine.schemas.tool_schemas import (  # noqa: E402
    ToolCall,
    ToolExecutionContext,
)
from apps.docent.schemas.artwork_schemas import Artwork  # noqa: E402
from apps.docent.services.docent_discovery_service import (  # noqa: E402
    discover_docent_candidates,
)
from apps.docent.tools import docent_tool_registry  # noqa: E402
from extensions.retrieval.schemas.chunk_schemas import (  # noqa: E402
    RetrievalChunk,
    RetrievedChunk,
    VectorRetrievalResult,
)
from extensions.retrieval.schemas.embedding_schemas import (  # noqa: E402
    IndexedChunkEmbedding,
)
from extensions.retrieval.schemas.index_schemas import (  # noqa: E402
    IndexedRetrievalChunk,
)


def retrieved(
    painting_index: int,
    *,
    score: float,
    suffix: str = "description",
) -> RetrievedChunk:
    reference = f"painting:{painting_index}"
    return RetrievedChunk(
        chunk=RetrievalChunk(
            chunk_id=f"{reference}:{suffix}",
            chunk_type=suffix,
            parent_document_id=reference,
            text=f"Evidence {painting_index} {suffix}.",
            title=f"Artwork {painting_index}",
            source_reference=reference,
            url=f"https://example.test/{painting_index}",
            metadata={"painting_index": painting_index},
        ),
        score=score,
    )


def artwork(painting_index: int, room_index: int) -> Artwork:
    return Artwork(
        painting_index=painting_index,
        title=f"Artwork {painting_index}",
        artist=f"Artist {painting_index}",
        room_index=room_index,
        room_name=f"Room {room_index}",
        description="Description.",
    )


class DocentDiscoveryVectorFilterTest(unittest.TestCase):
    @patch(
        "docent.services.docent_vector_retrieval_service."
        "retrieve_chunks_by_vector_similarity"
    )
    @patch(
        "docent.services.docent_vector_retrieval_service."
        "get_docent_vector_index"
    )
    @patch(
        "docent.services.docent_vector_retrieval_service.generate_embedding",
        return_value=[1.0, 0.0],
    )
    def test_filters_index_and_embeddings_before_similarity(
        self,
        _generate,
        get_index,
        similarity,
    ) -> None:
        chunks = []
        embeddings = []
        for painting_index in (1, 2, 3):
            item = retrieved(painting_index, score=0.8)
            chunks.append(
                IndexedRetrievalChunk(
                    chunk=item.chunk,
                    embedding_text=item.chunk.text,
                )
            )
            embeddings.append(
                IndexedChunkEmbedding(
                    chunk_id=item.chunk.chunk_id,
                    embedding_text=item.chunk.text,
                    model="test",
                    dimensions=2,
                    embedding=[1.0, 0.0],
                )
            )
        get_index.return_value = chunks, embeddings
        similarity.return_value = []

        from apps.docent.services.docent_vector_retrieval_service import (
            retrieve_docent_chunks_by_vector_similarity,
        )

        retrieve_docent_chunks_by_vector_similarity(
            query="loose brushwork",
            use_hybrid_scoring=False,
            expand_parent_documents=False,
            apply_confidence_gate=False,
            allowed_references={"painting:1", "painting:2"},
            excluded_references={"painting:2"},
            allowed_chunk_types={"description"},
        )

        kwargs = similarity.call_args.kwargs
        self.assertEqual(
            [item.chunk.source_reference for item in kwargs["indexed_chunks"]],
            ["painting:1"],
        )
        self.assertEqual(
            [item.chunk_id for item in kwargs["chunk_embeddings"]],
            ["painting:1:description"],
        )


class DocentDiscoveryServiceTest(unittest.TestCase):
    @patch("docent.services.docent_discovery_service.get_painting_by_index")
    @patch(
        "docent.services.docent_discovery_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_groups_by_artwork_and_uses_proximity_only_within_score_band(
        self,
        retrieve,
        get_artwork,
    ) -> None:
        retrieve.return_value = VectorRetrievalResult(
            results=[
                retrieved(1, score=0.80),
                retrieved(1, score=0.78, suffix="provenance"),
                retrieved(2, score=0.79),
            ]
        )
        artworks = {
            1: artwork(1, 10),
            2: artwork(2, 6),
            9: artwork(9, 5),
        }
        get_artwork.side_effect = artworks.get

        result = discover_docent_candidates(
            query="aristocratic leisure",
            scope="collection",
            current_reference="painting:9",
            excluded_references={"painting:8", "painting:9"},
        )

        retrieve.assert_called_once()
        kwargs = retrieve.call_args.kwargs
        self.assertFalse(kwargs["use_hybrid_scoring"])
        self.assertFalse(kwargs["expand_parent_documents"])
        self.assertEqual(kwargs["min_confidence_score"], 0.49)
        self.assertFalse(kwargs["apply_confidence_gate"])
        self.assertEqual(
            kwargs["allowed_chunk_types"],
            {"description"},
        )
        self.assertEqual(
            kwargs["excluded_references"],
            {"painting:8", "painting:9"},
        )
        self.assertEqual(
            [candidate["reference"] for candidate in result["candidates"]],
            ["painting:2", "painting:1"],
        )
        self.assertEqual(len(result["candidates"][1]["evidence"]), 2)
        self.assertEqual(result["candidates"][0]["room_distance"], 1)
        telemetry = result["telemetry"]
        self.assertEqual(telemetry["threshold"], 0.49)
        self.assertEqual(
            [
                candidate["reference"]
                for candidate in telemetry["raw_candidates"]
            ],
            ["painting:1", "painting:2"],
        )
        self.assertEqual(
            [candidate["rank"] for candidate in telemetry["raw_candidates"]],
            [1, 2],
        )
        self.assertEqual(
            [
                candidate["selected_rank"]
                for candidate in telemetry["raw_candidates"]
            ],
            [2, 1],
        )

    @patch(
        "docent.services.docent_discovery_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_current_artwork_without_reference_does_not_search(
        self,
        retrieve,
    ) -> None:
        result = discover_docent_candidates(
            query="commissioning story",
            scope="current_artwork",
            current_reference=None,
        )
        retrieve.assert_not_called()
        self.assertFalse(result["retrieval_performed"])
        self.assertEqual(result["candidates"], [])

    @patch("docent.services.docent_discovery_service.get_painting_by_index")
    @patch(
        "docent.services.docent_discovery_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_current_artwork_search_is_restricted_to_that_artwork(
        self,
        retrieve,
        get_artwork,
    ) -> None:
        retrieve.return_value = VectorRetrievalResult(results=[])
        get_artwork.return_value = artwork(9, 5)

        result = discover_docent_candidates(
            query="unusual commissioning circumstances",
            scope="current_artwork",
            current_reference="painting:9",
        )

        kwargs = retrieve.call_args.kwargs
        self.assertEqual(kwargs["allowed_references"], {"painting:9"})
        self.assertIsNone(kwargs["excluded_references"])
        self.assertEqual(
            kwargs["allowed_chunk_types"],
            {"description", "provenance"},
        )
        self.assertTrue(result["retrieval_performed"])
        self.assertEqual(result["candidates"], [])


class DocentDiscoveryToolTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()

    @staticmethod
    def _empty_discovery(scope: str) -> dict:
        return {
            "query": "unexplored meaning",
            "scope": scope,
            "current_reference": None,
            "retrieval_performed": True,
            "retrieval_timings": {"total_seconds": 0.01},
            "telemetry": {
                "query": "unexplored meaning",
                "scope": scope,
                "threshold": 0.49,
                "raw_candidates": [],
            },
            "candidates": [],
        }

    @patch("docent.tools.discovery_tool.discover_docent_candidates")
    def test_proactive_discovery_blocked_before_answer_without_retrieval(
        self,
        discover,
    ) -> None:
        conversation = create_conversation()

        result = docent_tool_registry.execute(
            ToolCall(
                name="discover_docent_knowledge",
                arguments={
                    "query": "unexplored meaning",
                    "scope": "current_artwork",
                    "purpose": "proactive",
                },
            ),
            ToolExecutionContext(
                conversation_id=conversation.conversation_id,
                visitor_sentence_emitted=False,
                executed_tool_names=[],
            ),
        )

        discover.assert_not_called()
        self.assertFalse(result.success)
        self.assertFalse(result.retrieval_used)
        self.assertIn("post-answer discovery phase", result.message)

    @patch("docent.tools.discovery_tool.discover_docent_candidates")
    def test_discovery_allowed_after_answer(
        self,
        discover,
    ) -> None:
        conversation = create_conversation()
        discover.return_value = self._empty_discovery("current_artwork")

        result = docent_tool_registry.execute(
            ToolCall(
                name="discover_docent_knowledge",
                arguments={
                    "query": "unexplored meaning",
                    "scope": "current_artwork",
                    "purpose": "proactive",
                },
            ),
            ToolExecutionContext(
                conversation_id=conversation.conversation_id,
                visitor_sentence_emitted=True,
                response_phase="post_answer",
                executed_tool_names=["retrieve_docent_knowledge"],
            ),
        )

        discover.assert_called_once()
        self.assertTrue(result.success)
        self.assertTrue(result.retrieval_used)

    @patch("docent.tools.discovery_tool.discover_docent_candidates")
    def test_delegated_discovery_allowed_before_answer(
        self,
        discover,
    ) -> None:
        conversation = create_conversation()
        discover.return_value = self._empty_discovery("collection")

        result = docent_tool_registry.execute(
            ToolCall(
                name="discover_docent_knowledge",
                arguments={
                    "query": "what to see next",
                    "scope": "collection",
                    "purpose": "delegated",
                },
            ),
            ToolExecutionContext(
                conversation_id=conversation.conversation_id,
                visitor_sentence_emitted=False,
                executed_tool_names=[],
            ),
        )

        discover.assert_called_once()
        self.assertTrue(result.success)

    @patch("docent.tools.discovery_tool.discover_docent_candidates")
    def test_collection_scope_excludes_visited_and_never_updates_dialogue(
        self,
        discover,
    ) -> None:
        conversation = create_conversation()
        add_dialogue_turn(
            conversation.conversation_id,
            user="Tell me about one.",
            reference=["painting:1"],
        )
        add_dialogue_turn(
            conversation.conversation_id,
            user="Now this one.",
            reference=["painting:2"],
        )
        discover.return_value = {
            "query": "loose brushwork",
            "scope": "collection",
            "current_reference": "painting:2",
            "retrieval_performed": True,
            "retrieval_timings": {"total_seconds": 0.01},
            "telemetry": {
                "query": "loose brushwork",
                "scope": "collection",
                "threshold": 0.49,
                "raw_candidates": [],
            },
            "candidates": [
                {
                    "painting_index": 3,
                    "reference": "painting:3",
                    "title": "Artwork 3",
                    "artist": "Artist 3",
                    "semantic_score": 0.73,
                    "room_index": 4,
                    "room_name": "Room 4",
                    "room_distance": 2,
                    "evidence": [
                        {
                            "text": "Loose brushwork evidence.",
                            "score": 0.73,
                            "url": "https://example.test/3",
                        }
                    ],
                }
            ],
        }

        result = docent_tool_registry.execute(
            ToolCall(
                name="discover_docent_knowledge",
                arguments={
                    "query": "loose brushwork",
                    "scope": "collection",
                },
            ),
            ToolExecutionContext(
                conversation_id=conversation.conversation_id,
                visitor_sentence_emitted=True,
                response_phase="post_answer",
            ),
        )

        discover.assert_called_once_with(
            query="loose brushwork",
            scope="collection",
            current_reference="painting:2",
            excluded_references={"painting:1", "painting:2"},
        )
        self.assertTrue(result.success)
        self.assertTrue(result.retrieval_used)
        self.assertIsNone(result.dialogue_state)
        self.assertEqual(result.sources[0].reference, "painting:3")
        self.assertNotIn("sources", result.model_payload())
        self.assertNotIn("dialogue_state", result.model_payload())
        self.assertNotIn("telemetry", result.model_payload())
        self.assertEqual(result.telemetry["threshold"], 0.49)

    def test_tool_is_registered_with_semantic_scopes(self) -> None:
        definition = next(
            definition
            for definition in docent_tool_registry.get_definitions()
            if definition.name == "discover_docent_knowledge"
        )
        self.assertIn("conceptual semantic discovery", definition.description)
        self.assertIn("Subject Transition Point", definition.description)
        self.assertIn("transitioning prematurely", definition.description)
        self.assertIn("delegates the choice", definition.description)
        self.assertEqual(
            definition.allowed_phases,
            {"primary", "post_answer"},
        )
        self.assertEqual(
            definition.parameters["properties"]["scope"]["enum"],
            ["current_artwork", "collection"],
        )
        self.assertEqual(
            definition.parameters["properties"]["purpose"]["enum"],
            ["proactive", "delegated"],
        )


if __name__ == "__main__":
    unittest.main()
