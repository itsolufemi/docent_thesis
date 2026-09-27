from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from conversation_core.schemas.conversation_schemas import DialogueTurn  # noqa: E402
from docent.schemas.preference_schemas import DocentPreferenceState  # noqa: E402
from docent.services.docent_preference_analyser import (  # noqa: E402
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
                        "technical_depth_signal": "unchanged",
                        "verbosity_signal": "unchanged",
                    }
                )
                self.assertEqual(evidence.interest_signals[0].category, category)
                self.assertIsNone(debug["validation_error"])

    def test_technique_interest_does_not_imply_technical_depth(self) -> None:
        (evidence, _), _ = self.analyse(
            {
                "interest_signals": [
                    {"category": "technique", "strength": "strong"}
                ],
                "technical_depth_signal": "unchanged",
                "verbosity_signal": "unchanged",
            },
            "How did the artist make those brush marks?",
        )
        self.assertEqual(evidence.technical_depth_signal, "unchanged")

    def test_depth_and_verbosity_signals_are_independent(self) -> None:
        (evidence, _), _ = self.analyse(
            {
                "interest_signals": [],
                "technical_depth_signal": "low",
                "verbosity_signal": "low",
            },
            "Can you explain more simply and briefly?",
        )
        self.assertEqual(evidence.technical_depth_signal, "low")
        self.assertEqual(evidence.verbosity_signal, "low")

    def test_context_is_present_for_contextual_follow_up(self) -> None:
        (_, _), prompt = self.analyse(
            {
                "interest_signals": [],
                "technical_depth_signal": "unchanged",
                "verbosity_signal": "unchanged",
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
