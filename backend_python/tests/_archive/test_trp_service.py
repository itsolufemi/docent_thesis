import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))


from conversation_core.services.trp_service import (
    TRP_REQUEST_OPTIONS,
    TRP_RESPONSE_FORMAT,
    predict_transition_relevance,
)


class FakeStreamingResponse:
    def __init__(
        self,
        chunks: list[dict],
    ) -> None:
        self.chunks = chunks
        self.closed = False
        self.lines_read = 0

    def __enter__(self):
        return self

    def __exit__(
        self,
        exception_type,
        exception,
        traceback,
    ) -> None:
        self.closed = True

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        for chunk in self.chunks:
            self.lines_read += 1
            yield json.dumps(chunk)

    def close(self) -> None:
        self.closed = True


class TRPServiceTest(unittest.TestCase):
    @patch(
        "conversation_core.services.trp_service."
        "settings"
    )
    @patch(
        "conversation_core.services.trp_service."
        "httpx.stream"
    )
    def test_uses_balanced_streaming_profile_and_returns_early(
        self,
        stream_request,
        mock_settings,
    ) -> None:
        mock_settings.ollama_base_url = (
            "http://localhost:11434"
        )
        mock_settings.ollama_trp_model = (
            "gemma4:cloud"
        )
        response = FakeStreamingResponse(
            [
                {
                    "response": (
                        '{"trp_probability":0.91,'
                    ),
                    "done": False,
                },
                {
                    "response": (
                        '"turn_complete":true,'
                        '"reason":"Complete request."}'
                    ),
                    "done": False,
                },
                {
                    "response": "",
                    "done": True,
                },
            ]
        )
        stream_request.return_value = response

        prediction = predict_transition_relevance(
            partial_utterance=(
                "Tell me about The Arab Tent."
            ),
        )

        self.assertTrue(
            prediction.turn_complete
        )
        self.assertEqual(
            prediction.trp_probability,
            0.91,
        )
        self.assertEqual(response.lines_read, 2)
        self.assertTrue(response.closed)

        request_arguments = (
            stream_request.call_args.kwargs
        )
        request_payload = request_arguments["json"]

        self.assertTrue(
            request_payload["stream"]
        )
        self.assertFalse(
            request_payload["think"]
        )
        self.assertEqual(
            request_payload["format"],
            TRP_RESPONSE_FORMAT,
        )
        self.assertEqual(
            request_payload["options"],
            TRP_REQUEST_OPTIONS,
        )

    @patch(
        "conversation_core.services.trp_service."
        "settings"
    )
    @patch(
        "conversation_core.services.trp_service."
        "httpx.stream"
    )
    def test_threshold_remains_authoritative(
        self,
        stream_request,
        mock_settings,
    ) -> None:
        mock_settings.ollama_base_url = (
            "http://localhost:11434"
        )
        mock_settings.ollama_trp_model = (
            "gemma4:cloud"
        )
        stream_request.return_value = (
            FakeStreamingResponse(
                [
                    {
                        "response": json.dumps(
                            {
                                "trp_probability": (
                                    0.2
                                ),
                                "turn_complete": (
                                    True
                                ),
                                "reason": (
                                    "Incomplete clause."
                                ),
                            }
                        ),
                        "done": False,
                    },
                ]
            )
        )

        prediction = predict_transition_relevance(
            partial_utterance="Tell me about",
        )

        self.assertFalse(
            prediction.turn_complete
        )

    @patch(
        "conversation_core.services.trp_service."
        "settings"
    )
    @patch(
        "conversation_core.services.trp_service."
        "httpx.stream"
    )
    def test_rejects_stream_without_valid_json(
        self,
        stream_request,
        mock_settings,
    ) -> None:
        mock_settings.ollama_base_url = (
            "http://localhost:11434"
        )
        mock_settings.ollama_trp_model = (
            "gemma4:cloud"
        )
        stream_request.return_value = (
            FakeStreamingResponse(
                [
                    {
                        "response": "not JSON",
                        "done": False,
                    },
                    {
                        "response": "",
                        "done": True,
                    },
                ]
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "without producing valid structured JSON",
        ):
            predict_transition_relevance(
                partial_utterance="Tell me",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
