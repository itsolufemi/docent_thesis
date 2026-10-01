from __future__ import annotations

import sys
import unittest

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from conversation_core.prompts.core_prompt_profile import (  # noqa: E402
    CORE_BEHAVIOURAL_RULES,
)
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    DialogueTurn,
)
from docent.services.docent_prompt_service import (  # noqa: E402
    DOCENT_ASSISTANT_ROLE,
    DOCENT_BEHAVIOURAL_RULES,
    DOCENT_CONTENT_GENERATION_RULES,
    DOCENT_DISCOVERY_POLICY_RULES,
    DOCENT_PROMPT_PROFILE,
    docent_build_prompt,
)


class DocentPromptProfileTest(unittest.TestCase):
    def test_docent_profile_composes_core_and_domain_rules(self) -> None:
        expected_rules = [
            *CORE_BEHAVIOURAL_RULES,
            *DOCENT_BEHAVIOURAL_RULES,
        ]

        self.assertEqual(
            DOCENT_PROMPT_PROFILE.assistant_role,
            DOCENT_ASSISTANT_ROLE,
        )
        self.assertEqual(
            DOCENT_PROMPT_PROFILE.behavioural_rules,
            expected_rules,
        )
        self.assertEqual(
            len(expected_rules),
            len(set(expected_rules)),
        )

    def test_rendered_prompt_contains_both_rule_layers_and_context(self) -> None:
        prompt = docent_build_prompt(
            user_input="Tell me more.",
            dialogue_history=[
                DialogueTurn(
                    subject=["The Swing"],
                    user="Tell me more.",
                )
            ],
            response_guidance="Use the supplied evidence.",
        )

        self.assertIn(DOCENT_ASSISTANT_ROLE, prompt)
        self.assertIn(CORE_BEHAVIOURAL_RULES[0], prompt)
        self.assertIn(DOCENT_BEHAVIOURAL_RULES[0], prompt)
        self.assertIn(DOCENT_CONTENT_GENERATION_RULES[0], prompt)
        self.assertLess(
            prompt.index(CORE_BEHAVIOURAL_RULES[0]),
            prompt.index(DOCENT_BEHAVIOURAL_RULES[0]),
        )
        self.assertIn("Behavioural policy:", prompt)
        self.assertIn("Content-generation policy:", prompt)
        self.assertIn("Discovery policy:", prompt)
        self.assertIn(DOCENT_DISCOVERY_POLICY_RULES[0], prompt)
        self.assertLess(
            prompt.index("Content-generation policy:"),
            prompt.index("Discovery policy:"),
        )
        self.assertLess(
            prompt.index("Discovery policy:"),
            prompt.index("Context:"),
        )
        self.assertIn(
            "Response guidance:\nUse the supplied evidence.",
            prompt,
        )
        self.assertIn("Recent dialogue:", prompt)
        self.assertIn("Visitor: Tell me more.", prompt)

    def test_fixed_story_and_length_rules_are_removed(self) -> None:
        content_policy = " ".join(DOCENT_CONTENT_GENERATION_RULES)
        self.assertNotIn("what story it tells", content_policy)
        self.assertNotIn("two to eight", content_policy)

    def test_discovery_policy_requires_answer_first_and_evidence_before_offer(
        self,
    ) -> None:
        policy = " ".join(DOCENT_DISCOVERY_POLICY_RULES)
        self.assertIn(
            "answer the visitor's explicit request before pursuing an optional discovery",
            policy,
        )
        self.assertIn(
            "at least one complete visitor-facing answer sentence",
            policy,
        )
        self.assertIn("Never mention or tease", policy)
        self.assertIn("at most one selective discovery", policy)
        self.assertIn("do not force a discovery suggestion", policy)
        self.assertIn("Do not run discovery on a routine first request", policy)
        self.assertIn("delegates the choice", policy)
        self.assertIn("select one concrete artwork", policy)
        self.assertIn("rather than offering categories", policy)
        self.assertIn("ignore or decline", policy)


if __name__ == "__main__":
    unittest.main()
