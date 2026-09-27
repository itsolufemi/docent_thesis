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
from docent.services.docent_prompt_service import (  # noqa: E402
    build_docent_content_policy_debug,
    docent_build_prompt,
)


class DocentPreferencePromptTest(unittest.TestCase):
    def test_default_state_produces_neutral_content_policy(self) -> None:
        prompt = docent_build_prompt("Hello", [])
        self.assertNotIn("Visitor preferences this session", prompt)
        self.assertIn("Content-generation policy:", prompt)
        self.assertIn("No interest currently has clear priority", prompt)
        self.assertIn("four to six short spoken sentences", prompt)

    def test_docent_grounding_uses_retrieval_without_a_knowledge_ceiling(
        self,
    ) -> None:
        prompt = docent_build_prompt("Tell me about this artwork.", [])

        self.assertNotIn(
            "You know the artwork only through the information provided",
            prompt,
        )
        self.assertNotIn(
            "do not introduce claims that the available evidence does not support",
            prompt,
        )
        self.assertIn(
            "primary grounding for factual claims about specific artworks",
            prompt,
        )
        self.assertIn("use your own underlying knowledge", prompt)
        self.assertIn(
            "Do not treat retrieved information as the complete boundary",
            prompt,
        )
        self.assertIn("Do not invent artwork-specific facts", prompt)
        self.assertIn("prefer the retrieved information", prompt)
        self.assertIn("Clearly qualify interpretation", prompt)
        self.assertIn("Apply this priority order", prompt)

    def test_technique_dominant_state_becomes_actionable_policy(self) -> None:
        state = DocentPreferenceState(
            interests={
                "interpretation": 0.1,
                "technique": 0.5,
                "historical_social_context": 0.1,
                "narrative": 0.2,
                "artist_context": 0.1,
            },
        )
        with use_docent_preference_state(state):
            prompt = docent_build_prompt("How was it painted?", [])

        self.assertNotIn("Visitor preferences this session", prompt)
        self.assertIn(
            "strongest current inferred interest is technique and formal qualities",
            prompt,
        )
        self.assertIn("foreground that lens", prompt)
        self.assertIn("explicit current question", prompt)
        self.assertIn("relative priorities, not proportions", prompt)
        self.assertIn(
            "preferred lens is not well covered by the retrieved information",
            prompt,
        )
        self.assertIn(
            "use relevant general knowledge where appropriate",
            prompt,
        )
        self.assertIn(
            "broader model knowledge may be used to explain technique",
            prompt,
        )

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

        self.assertIn(
            "strongest current inferred interest is interpretation and meaning",
            interpretation_prompt,
        )
        self.assertIn(
            "strongest current inferred interest is technique and formal qualities",
            technique_prompt,
        )
        self.assertNotEqual(interpretation_prompt, technique_prompt)

    def test_policy_debug_exposes_three_stage_diagnostics(self) -> None:
        debug = build_docent_content_policy_debug(
            DocentPreferenceState(
                interests={
                    "interpretation": 0.14,
                    "technique": 0.44,
                    "historical_social_context": 0.14,
                    "narrative": 0.14,
                    "artist_context": 0.14,
                }
            )
        )
        self.assertEqual(debug["dominant_interest"]["category"], "technique")
        self.assertEqual(debug["mode"], "adaptive")
        self.assertEqual(
            set(debug),
            {"dominant_interest", "ordered_interests", "mode"},
        )

    def test_observed_dialogue_progression_changes_open_ended_policy(
        self,
    ) -> None:
        neutral_prompt = docent_build_prompt(
            "Tell me about The Arab Tent.",
            [],
        )
        learned_state = DocentPreferenceState(
            interests={
                "interpretation": 0.1425,
                "technique": 0.43,
                "historical_social_context": 0.1425,
                "narrative": 0.1425,
                "artist_context": 0.1425,
            }
        )
        stronger_state = DocentPreferenceState(
            interests={
                "interpretation": 0.19,
                "technique": 0.54,
                "historical_social_context": 0.09,
                "narrative": 0.09,
                "artist_context": 0.09,
            }
        )
        with use_docent_preference_state(learned_state):
            faust_prompt = docent_build_prompt(
                "Tell me about Faust and Mephistopheles.",
                [],
            )
        with use_docent_preference_state(stronger_state):
            victoria_prompt = docent_build_prompt(
                "Tell me about the Queen Victoria portrait.",
                [],
            )

        self.assertIn(
            "No interest currently has clear priority",
            neutral_prompt,
        )
        for adaptive_prompt in (faust_prompt, victoria_prompt):
            self.assertIn(
                "strongest current inferred interest is technique",
                adaptive_prompt,
            )
            self.assertIn("foreground that lens", adaptive_prompt)


if __name__ == "__main__":
    unittest.main()
