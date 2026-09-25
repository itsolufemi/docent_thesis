from __future__ import annotations

import unittest

from conversation_core.prompts.core_prompt_profile import (
    CORE_BEHAVIOURAL_RULES,
    DEFAULT_ASSISTANT_ROLE,
)


class CorePromptProfileTest(unittest.TestCase):
    def test_core_profile_is_domain_neutral(self) -> None:
        self.assertEqual(len(CORE_BEHAVIOURAL_RULES), 8)
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


if __name__ == "__main__":
    unittest.main()
