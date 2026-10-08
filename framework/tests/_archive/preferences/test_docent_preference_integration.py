from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from core_engine.schemas.query_schemas import QueryResult  # noqa: E402
from apps.docent.schemas.preference_schemas import (  # noqa: E402
    DocentInterestSignal,
    DocentPreferenceEvidence,
)
from apps.docent.services.docent_preference_service import (  # noqa: E402
    get_active_docent_preference_state,
)
from apps.docent.services.docent_preference_store import DocentPreferenceStore  # noqa: E402
from apps.docent.services.docent_query_service import (  # noqa: E402
    DocentPreferenceQueryService,
)


class FakeQueryEngine:
    direct_routing_enabled = True

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.states_seen = []

    def generate_streaming_response(self, **kwargs) -> QueryResult:
        self.states_seen.append(get_active_docent_preference_state())
        self.events.append("response")
        callback = kwargs.get("on_stream_event")
        if callback is not None:
            self.events.append("first_audio_path_available")
        return QueryResult(
            request=kwargs["text"],
            response="Answer",
            conversation_id=kwargs.get("conversation_id") or "created-id",
        )

    def generate_response(self, **kwargs) -> QueryResult:
        self.states_seen.append(get_active_docent_preference_state())
        self.events.append("response")
        return QueryResult(
            request=kwargs["text"],
            response="Answer",
            conversation_id=kwargs.get("conversation_id") or "created-id",
        )


class DocentPreferenceIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.events: list[str] = []
        self.store = DocentPreferenceStore()
        self.engine = FakeQueryEngine(self.events)
        self.signal_categories = iter(
            ["technique", "historical_social_context"]
        )

        def analyser(history, text, state):
            del history, text, state
            self.events.append("analysis")
            return (
                DocentPreferenceEvidence(
                    interest_signals=[
                        DocentInterestSignal(
                            category=next(self.signal_categories),
                            strength="strong",
                        )
                    ]
                ),
                {"test": True},
            )

        self.service = DocentPreferenceQueryService(
            self.engine,
            analyser=analyser,
            preference_store=self.store,
        )

    @patch("docent.services.docent_query_service.append_telemetry_log")
    def test_response_uses_old_state_and_update_affects_next_turn(
        self,
        telemetry,
    ) -> None:
        self.service.generate_streaming_response(
            text="How was it painted?",
            conversation_id="conversation",
            request_id="one",
            on_stream_event=lambda event: None,
        )
        self.assertEqual(self.events[:3], [
            "response",
            "first_audio_path_available",
            "analysis",
        ])
        self.assertAlmostEqual(
            self.engine.states_seen[0].interests["technique"],
            0.2,
        )
        self.assertAlmostEqual(
            self.store.get("conversation").interests["technique"],
            0.36,
        )

        self.service.generate_streaming_response(
            text="What was happening historically?",
            conversation_id="conversation",
            request_id="two",
        )
        self.assertAlmostEqual(
            self.engine.states_seen[1].interests["technique"],
            0.36,
        )
        self.assertLess(
            self.store.get("conversation").interests["technique"],
            0.36,
        )
        self.assertEqual(telemetry.call_count, 2)
        payload = telemetry.call_args.kwargs["payload"]
        self.assertIn("preference_state_used", payload)
        self.assertIn("evidence", payload)
        self.assertIn("next_preference_state", payload)
        self.assertIn("policy_used", payload)
        self.assertNotIn("analysis", payload)
        self.assertNotIn("technical_depth_changed", payload)
        self.assertNotIn("verbosity_changed", payload)
        self.assertEqual(
            payload["policy_used"]["dominant_interest"]["category"],
            "technique",
        )
        self.assertEqual(
            payload["preference_state_used"]["interests"]["technique"],
            0.36,
        )
        self.assertLess(
            payload["next_preference_state"]["interests"]["technique"],
            0.36,
        )

    @patch("docent.services.docent_query_service.append_telemetry_log")
    def test_new_conversation_is_stored_under_returned_id(self, telemetry) -> None:
        result = self.service.generate_response(
            text="Tell me about the composition.",
            conversation_id=None,
        )
        self.assertEqual(result.conversation_id, "created-id")
        self.assertAlmostEqual(
            self.engine.states_seen[0].interests["technique"],
            0.2,
        )
        self.assertGreater(
            self.store.get("created-id").interests["technique"],
            0.2,
        )
        telemetry.assert_called_once()

    @patch("docent.services.docent_query_service.append_telemetry_log")
    def test_preferences_are_isolated_by_conversation(self, telemetry) -> None:
        self.service.generate_response("One", conversation_id="a")
        self.service.generate_response("Two", conversation_id="b")
        self.assertGreater(self.store.get("a").interests["technique"], 0.2)
        self.assertEqual(self.store.get("b").interests["technique"], 0.16)
        self.assertGreater(
            self.store.get("b").interests["historical_social_context"],
            0.2,
        )


if __name__ == "__main__":
    unittest.main()
