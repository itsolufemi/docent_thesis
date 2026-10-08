from __future__ import annotations

import unittest

from pydantic import ValidationError

from core_engine.default_profile_definition.default_profile_definition import (
    CORE_BEHAVIOURAL_RULES,
    CORE_CONVERSATIONAL_RULES,
    DEFAULT_ASSISTANT_ROLE,
    DIRECT_ROUTING_RULES,
)
from core_engine.schemas.prompt_schemas import (
    PromptProfile,
)
from core_engine.services.prompt_service import build_prompt


class CorePromptProfileTest(unittest.TestCase):
    def test_prompt_profile_requires_an_explicit_assistant_role(self) -> None:
        with self.assertRaises(ValidationError):
            PromptProfile()

    def test_core_profile_is_domain_neutral(self) -> None:
        self.assertEqual(len(CORE_CONVERSATIONAL_RULES), 9)
        self.assertEqual(
            CORE_BEHAVIOURAL_RULES,
            [
                *CORE_CONVERSATIONAL_RULES,
                *DIRECT_ROUTING_RULES,
            ],
        )
        self.assertIn("conversational AI assistant", DEFAULT_ASSISTANT_ROLE)

        core_text = " ".join(CORE_BEHAVIOURAL_RULES).lower()

        for domain_term in (
            "artwork",
            "painting",
            "visitor",
            "wallace collection",
            "artist",
        ):
            self.assertNotIn(domain_term, core_text)

    def test_core_rules_preserve_repair_and_evidential_discipline(self) -> None:
        core_text = " ".join(CORE_BEHAVIOURAL_RULES)

        self.assertIn(
            "change the explanation rather than repeating the same answer",
            core_text,
        )
        self.assertIn(
            "qualify interpretations, inferences, uncertain claims",
            core_text,
        )
        self.assertIn(
            "shortest natural repair response possible",
            core_text,
        )
        self.assertIn(
            "around four to six short spoken sentences",
            core_text,
        )

    def test_content_policy_uses_profile_default_or_application_override(
        self,
    ) -> None:
        profile = PromptProfile(
            assistant_role="You are a test assistant.",
            behavioural_rules=["Behave consistently."],
            default_content_generation_rules=["Use the default policy."],
        )
        default_prompt = build_prompt("Hello", [], profile)
        override_prompt = build_prompt(
            "Hello",
            [],
            profile,
            content_generation_rules=["Use the application policy."],
        )

        self.assertIn("Behavioural policy:", default_prompt)
        self.assertIn("Content-generation policy:", default_prompt)
        self.assertIn("Use the default policy.", default_prompt)
        self.assertNotIn("Use the default policy.", override_prompt)
        self.assertIn("Use the application policy.", override_prompt)


if __name__ == "__main__":
    unittest.main()
