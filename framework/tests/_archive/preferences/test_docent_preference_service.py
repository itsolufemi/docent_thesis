from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from apps.docent.schemas.preference_schemas import (  # noqa: E402
    DocentInterestSignal,
    DocentPreferenceEvidence,
    DocentPreferenceState,
)
from apps.docent.services.docent_preference_service import (  # noqa: E402
    apply_docent_preference_evidence,
    update_docent_preferences,
)
from apps.docent.services.docent_preference_store import (  # noqa: E402
    DocentPreferenceStore,
)


class DocentPreferenceServiceTest(unittest.TestCase):
    def test_defaults_are_uniform_and_interest_only(self) -> None:
        state = DocentPreferenceState()
        self.assertEqual(set(state.interests.values()), {0.2})
        self.assertAlmostEqual(sum(state.interests.values()), 1.0)
        self.assertEqual(
            state.model_dump(mode="json"),
            {"interests": state.interests},
        )

    def test_strong_technique_signal_updates_and_normalises(self) -> None:
        updated = apply_docent_preference_evidence(
            DocentPreferenceState(),
            DocentPreferenceEvidence(
                interest_signals=[
                    DocentInterestSignal(
                        category="technique",
                        strength="strong",
                    )
                ]
            ),
        )
        self.assertAlmostEqual(updated.interests["technique"], 0.36)
        for category, weight in updated.interests.items():
            if category != "technique":
                self.assertAlmostEqual(weight, 0.16)

    def test_repeated_and_competing_signals_remain_stable(self) -> None:
        state = DocentPreferenceState()
        technique = DocentPreferenceEvidence(
            interest_signals=[
                DocentInterestSignal(
                    category="technique",
                    strength="strong",
                )
            ]
        )
        state = apply_docent_preference_evidence(state, technique)
        first_technique = state.interests["technique"]
        state = apply_docent_preference_evidence(state, technique)
        self.assertGreater(state.interests["technique"], first_technique)

        history = DocentPreferenceEvidence(
            interest_signals=[
                DocentInterestSignal(
                    category="historical_social_context",
                    strength="strong",
                )
            ]
        )
        previous_technique = state.interests["technique"]
        state = apply_docent_preference_evidence(state, history)
        self.assertGreater(
            state.interests["historical_social_context"],
            0.0,
        )
        self.assertLess(state.interests["technique"], previous_technique)
        self.assertAlmostEqual(sum(state.interests.values()), 1.0)
        self.assertTrue(all(value >= 0 for value in state.interests.values()))

    def test_empty_evidence_is_unchanged(self) -> None:
        state = DocentPreferenceState()
        self.assertEqual(
            apply_docent_preference_evidence(
                state,
                DocentPreferenceEvidence(),
            ),
            state,
        )

    def test_store_isolates_conversations_and_returns_copies(self) -> None:
        store = DocentPreferenceStore()
        evidence = DocentPreferenceEvidence(
            interest_signals=[
                DocentInterestSignal(
                    category="technique",
                    strength="strong",
                )
            ]
        )
        update_docent_preferences("a", evidence, store=store)
        self.assertGreater(store.get("a").interests["technique"], 0.2)
        self.assertEqual(store.get("b").interests["technique"], 0.2)

        retrieved = store.get("a")
        retrieved.interests["technique"] = 99
        self.assertNotEqual(store.get("a").interests["technique"], 99)


if __name__ == "__main__":
    unittest.main()
