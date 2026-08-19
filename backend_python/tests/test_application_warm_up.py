import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from models.google_tts.google_tts_service import (
    GoogleTextToSpeechService,
)
from conversation_core.services.llm_service import (
    generate_llm_response,
    warm_up_main_llm,
)
from models.smart_turn.smart_turn_model_service import (
    SMART_TURN_SAMPLE_RATE,
    OnnxSmartTurnService,
)
from docent.services.docent_vector_retrieval_service import (
    warm_up_docent_retrieval,
)
from extensions.retrieval.schemas.chunk_schemas import (
    RetrievalTimings,
    VectorRetrievalResult,
)
from extensions.retrieval.services.embedding_service import (
    generate_embedding,
)


class ApplicationWarmUpTest(unittest.TestCase):
    @patch(
        "conversation_core.services.llm_service."
        "ollama_http_client"
    )
    def test_llm_requests_use_persistent_client(
        self,
        client,
    ) -> None:
        response = Mock()
        response.json.return_value = {"response": "ready"}
        client.post.return_value = response

        result = generate_llm_response("Warm request")

        self.assertEqual(result, "ready")
        client.post.assert_called_once()
        self.assertEqual(
            client.post.call_args.args[0],
            "/api/generate",
        )

    @patch(
        "extensions.retrieval.services.embedding_service."
        "ollama_http_client"
    )
    def test_embedding_uses_persistent_client(
        self,
        client,
    ) -> None:
        response = Mock()
        response.json.return_value = {
            "embedding": [0.1, 0.2]
        }
        client.post.return_value = response

        result = generate_embedding("The Swing")

        self.assertEqual(result, [0.1, 0.2])
        client.post.assert_called_once()
        self.assertEqual(
            client.post.call_args.args[0],
            "/api/embeddings",
        )

    @patch(
        "conversation_core.services.llm_service."
        "send_ollama_chat_request"
    )
    def test_main_llm_warm_up_uses_chat_path(
        self,
        send_chat,
    ) -> None:
        send_chat.return_value = {
            "message": {"content": "ready"}
        }

        result = warm_up_main_llm()

        self.assertEqual(result["response"], "ready")
        self.assertGreaterEqual(result["seconds"], 0)
        send_chat.assert_called_once_with(
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly: ready",
                }
            ],
            tools=None,
            think=False,
        )

    def test_google_tts_warm_up_consumes_stream(self) -> None:
        service = GoogleTextToSpeechService()
        service.stream_synthesise = Mock(
            return_value=iter([b"one", b"two"])
        )

        result = service.warm_up()

        service.stream_synthesise.assert_called_once_with(
            "Ready."
        )
        self.assertEqual(result["chunk_count"], 2)
        self.assertEqual(result["audio_bytes"], 6)
        self.assertIsNotNone(
            result["first_chunk_seconds"]
        )

    def test_smart_turn_warm_up_runs_silent_prediction(
        self,
    ) -> None:
        service = OnnxSmartTurnService.__new__(OnnxSmartTurnService)
        service.predict = Mock()

        duration = service.warm_up()

        self.assertGreaterEqual(duration, 0)
        pcm_audio = service.predict.call_args.args[0]
        self.assertEqual(
            len(pcm_audio),
            round(SMART_TURN_SAMPLE_RATE * 0.25) * 2,
        )
        self.assertEqual(
            service.predict.call_args.kwargs,
            {
                "sample_rate": SMART_TURN_SAMPLE_RATE,
                "channels": 1,
            },
        )

    @patch(
        "docent.services.docent_vector_retrieval_service."
        "retrieve_docent_chunks_by_vector_similarity"
    )
    def test_retrieval_warm_up_uses_fast_vector_path(
        self,
        retrieve,
    ) -> None:
        retrieve.return_value = VectorRetrievalResult(
            results=[],
            timings=RetrievalTimings(),
        )

        result = warm_up_docent_retrieval()

        self.assertEqual(result["result_count"], 0)
        retrieve.assert_called_once_with(
            query="The Swing",
            limit=1,
            expand_parent_documents=False,
            use_hybrid_scoring=False,
            apply_confidence_gate=False,
        )

    def test_warm_up_failures_are_isolated(self) -> None:
        from server import run_warm_up

        def fail() -> None:
            raise RuntimeError("unavailable")

        result = asyncio.run(run_warm_up("Test", fail))

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
