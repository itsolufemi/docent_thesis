from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from core_engine.schemas.conversation_schemas import DialogueTurn  # noqa: E402
from apps.docent.schemas.preference_schemas import DocentPreferenceState  # noqa: E402
from apps.docent.services.docent_preference_analyser import (  # noqa: E402
    analyse_docent_preferences,
)


class DocentPreferenceAnalyserTest(unittest.TestCase):
    def analyse(self, payload: dict, utterance: str = "Tell me more."):
        with patch(
            "docent.services.docent_preference_analyser.generate_llm_response",
            return_value=json.dumps(payload),
        ) as generate:
            result = analyse_docent_preferences(
                [DialogueTurn(user="How was it painted?", assistant="With oils.")],
                utterance,
                DocentPreferenceState(),
            )
        return result, generate.call_args.kwargs["prompt"]

    def test_parses_each_interest_category(self) -> None:
        for category in DocentPreferenceState().interests:
            with self.subTest(category=category):
                (evidence, debug), _ = self.analyse(
                    {
                        "interest_signals": [
                            {"category": category, "strength": "strong"}
                        ],
                    }
                )
                self.assertEqual(evidence.interest_signals[0].category, category)
                self.assertNotIn("validation_error", debug)
                self.assertNotIn("raw_response", debug)

    def test_technique_interest_is_parsed_without_secondary_signals(self) -> None:
        (evidence, _), _ = self.analyse(
            {
                "interest_signals": [
                    {"category": "technique", "strength": "strong"}
                ],
            },
            "How did the artist make those brush marks?",
        )
        self.assertEqual(len(evidence.interest_signals), 1)
        self.assertEqual(
            evidence.model_dump(mode="json"),
            {
                "interest_signals": [
                    {"category": "technique", "strength": "strong"}
                ]
            },
        )

    def test_context_is_present_for_contextual_follow_up(self) -> None:
        (_, _), prompt = self.analyse(
            {
                "interest_signals": [],
            },
            "Yes, tell me more.",
        )
        self.assertIn("Docent: With oils.", prompt)
        self.assertIn("Yes, tell me more.", prompt)

    def test_malformed_response_returns_empty_evidence(self) -> None:
        with patch(
            "docent.services.docent_preference_analyser.generate_llm_response",
            return_value="not json",
        ):
            evidence, debug = analyse_docent_preferences(
                [],
                "Hello",
                DocentPreferenceState(),
            )
        self.assertTrue(evidence.is_empty())
        self.assertIsNotNone(debug["validation_error"])


if __name__ == "__main__":
    unittest.main()
