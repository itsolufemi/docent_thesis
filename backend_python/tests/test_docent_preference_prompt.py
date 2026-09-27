from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from docent.schemas.preference_schemas import DocentPreferenceState  # noqa: E402
from docent.services.docent_preference_service import (  # noqa: E402
    use_docent_preference_state,
)
from docent.services.docent_prompt_service import docent_build_prompt  # noqa: E402


class DocentPreferencePromptTest(unittest.TestCase):
    def test_no_preference_section_without_active_docent_request(self) -> None:
        prompt = docent_build_prompt("Hello", [])
        self.assertNotIn("Visitor preferences this session", prompt)

    def test_active_state_is_rendered_as_soft_guidance(self) -> None:
        state = DocentPreferenceState(
            interests={
                "interpretation": 0.1,
                "technique": 0.5,
                "historical_social_context": 0.1,
                "narrative": 0.2,
                "artist_context": 0.1,
            },
            technical_depth="high",
            verbosity="low",
        )
        with use_docent_preference_state(state):
            prompt = docent_build_prompt("How was it painted?", [])

        self.assertIn("Visitor preferences this session", prompt)
        self.assertIn("technique: 0.50", prompt)
        self.assertIn("Technical depth: high", prompt)
        self.assertIn("Verbosity: low", prompt)
        self.assertIn("explicit current request first", prompt)
        self.assertIn("supported evidence", prompt)
        self.assertIn("soft guidance", prompt)
        self.assertIn("Verbosity controls the amount of detail", prompt)
        self.assertIn("technical depth controls", prompt)
        self.assertIn("Lower-weight interests remain available", prompt)

    def test_different_profiles_produce_different_emphasis_context(self) -> None:
        interpretation = DocentPreferenceState(
            interests={
                "interpretation": 0.6,
                "technique": 0.1,
                "historical_social_context": 0.1,
                "narrative": 0.1,
                "artist_context": 0.1,
            }
        )
        technique = DocentPreferenceState(
            interests={
                "interpretation": 0.1,
                "technique": 0.6,
                "historical_social_context": 0.1,
                "narrative": 0.1,
                "artist_context": 0.1,
            }
        )
        with use_docent_preference_state(interpretation):
            interpretation_prompt = docent_build_prompt("Tell me more", [])
        with use_docent_preference_state(technique):
            technique_prompt = docent_build_prompt("Tell me more", [])

        self.assertIn("interpretation: 0.60", interpretation_prompt)
        self.assertIn("technique: 0.60", technique_prompt)
        self.assertNotEqual(interpretation_prompt, technique_prompt)


if __name__ == "__main__":
    unittest.main()
