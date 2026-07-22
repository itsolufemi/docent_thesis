import os
import sys
import unittest
from pathlib import Path

BACKEND_PYTHON_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_PYTHON_ROOT))

from conversation_core.services.utterance_router_service import route_utterance
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
        "proposed_action": "create_bounded_branch",
    },
    {
        "text": "Stop the tour.",
        "route_type": "call_to_action",
        "requires_retrieval": False,
        "proposed_action": "close_bounded_branch",
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
