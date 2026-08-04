import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.services.utterance_router_service import (
    build_utterance_route_prompt,
    request_streaming_utterance_route,
    route_utterance,
)
from docent.config.docent_classifier_profile import docent_classifier_profile


RUN_CLASSIFIER_INTEGRATION_TESTS = (
    os.getenv("RUN_CLASSIFIER_INTEGRATION_TESTS", "").lower()
    in {"1", "true", "yes"}
)

CLASSIFIER_CASES = [
    {
        "text": "Hello, how are you?",
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
    },
    {
        "text": "Tell me about The Arab Tent.",
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
    },
    {
        "text": "Who was Fragonard?",
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
    },
    {
        "text": "Let's move to the next painting.",
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
    },
    {
        "text": "Give me a highlights tour.",
        "route_type": "call_to_action",
        "requires_retrieval": True,
        "proposed_action": "start_highlights_tour",
    },
    {
        "text": "Stop the tour.",
        "route_type": "call_to_action",
        "requires_retrieval": False,
        "proposed_action": "stop_tour",
    },
    {
        "text": "Wait, that's not what I meant.",
        "route_type": "interruption",
        "requires_retrieval": False,
        "proposed_action": None,
    },
    {
        "text": "!!!",
        "route_type": "noise",
        "requires_retrieval": False,
        "proposed_action": None,
    },
    {
        "text": "Compare The Arab Tent with Guernica.",
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
    },
]


class _FakeStreamingResponse:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        yield from self.lines

    def close(self) -> None:
        self.closed = True


class StreamingClassifierRequestTest(
    unittest.TestCase
):
    def test_uses_optimized_profile_and_returns_early(
        self,
    ) -> None:
        route_json = (
            '{"route_type":"response_request",'
            '"floor_intent":"take_floor",'
            '"requires_retrieval":true,'
            '"proposed_action":null,'
            '"candidate_subjects":["The Arab Tent"]}'
        )
        fake_response = _FakeStreamingResponse(
            [
                json.dumps(
                    {
                        "response": route_json[:80],
                        "done": False,
                    }
                ),
                json.dumps(
                    {
                        "response": route_json[80:],
                        "done": False,
                    }
                ),
                json.dumps(
                    {
                        "response": "unused",
                        "done": True,
                    }
                ),
            ]
        )

        with patch(
            (
                "conversation_core.services."
                "utterance_router_service.httpx.stream"
            ),
            return_value=fake_response,
        ) as stream_mock:
            route = request_streaming_utterance_route(
                prompt=build_utterance_route_prompt(
                    text=(
                        "Tell me about The Arab Tent."
                    ),
                    domain_profile=(
                        docent_classifier_profile
                    ),
                    compact_response=True,
                ),
                domain_profile=(
                    docent_classifier_profile
                ),
            )

        request_payload = (
            stream_mock.call_args.kwargs["json"]
        )
        self.assertTrue(
            request_payload["stream"]
        )
        self.assertFalse(
            request_payload["think"]
        )
        self.assertEqual(
            request_payload["format"]["type"],
            "object",
        )
        self.assertIn(
            "route_type",
            request_payload["format"][
                "required"
            ],
        )
        self.assertNotIn(
            "reason",
            request_payload["format"][
                "properties"
            ],
        )
        self.assertTrue(fake_response.closed)
        self.assertEqual(
            route.route_type,
            "response_request",
        )
        self.assertTrue(
            route.requires_retrieval
        )
        self.assertEqual(
            route.confidence,
            0.5,
        )
        self.assertEqual(
            route.reason,
            "No reason provided.",
        )


@unittest.skipUnless(
    RUN_CLASSIFIER_INTEGRATION_TESTS,
    (
        "Set RUN_CLASSIFIER_INTEGRATION_TESTS=1 to call the configured "
        "classifier model."
    ),
)
class DomainUtteranceClassifierIntegrationTest(unittest.TestCase):
    def test_docent_classifier_cases(self) -> None:
        results = []

        for case in CLASSIFIER_CASES:
            with self.subTest(text=case["text"]):
                result = route_utterance(
                    text=case["text"],
                    domain_profile=docent_classifier_profile,
                )
                results.append((case["text"], result))

                self.assertEqual(result.route_type, case["route_type"])
                self.assertEqual(
                    result.requires_retrieval,
                    case["requires_retrieval"],
                )
                self.assertEqual(
                    result.proposed_action,
                    case["proposed_action"],
                )

                candidate_text = " ".join(
                    result.candidate_subjects
                ).lower()

                if "The Arab Tent" in case["text"]:
                    self.assertIn("arab tent", candidate_text)

                if "Guernica" in case["text"]:
                    self.assertIn("guernica", candidate_text)

        print("\nDocent classifier evaluation")
        for text, result in results:
            print(
                f"{text!r}: route={result.route_type}, "
                f"retrieval={result.requires_retrieval}, "
                f"action={result.proposed_action}, "
                f"subjects={result.candidate_subjects}, "
                f"confidence={result.confidence}, "
                f"seconds={result.routing_seconds}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
