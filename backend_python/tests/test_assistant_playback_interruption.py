from __future__ import annotations

import tempfile
import unittest

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from conversation_core.api.routes_turn_buffer_stream import (
    create_turn_buffer_stream_router,
)
from conversation_core.memory.conversation_store import (
    add_dialogue_turn,
    conversations,
    create_conversation,
    update_dialogue_turn_context,
    update_interrupted_assistant_response,
    mark_dialogue_turn_interrupted,
)
from conversation_core.services.conversation_log_service import (
    append_telemetry_log,
)


class AssistantPlaybackInterruptionTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.log_root = Path(self.temporary_directory.name)
        self.directory_patch = patch(
            "conversation_core.services.conversation_log_service."
            "settings.conversation_log_directory",
            self.log_root,
        )
        self.enabled_patch = patch(
            "conversation_core.services.conversation_log_service."
            "settings.conversation_logging_enabled",
            True,
        )
        self.directory_patch.start()
        self.enabled_patch.start()

    def tearDown(self) -> None:
        self.enabled_patch.stop()
        self.directory_patch.stop()
        self.temporary_directory.cleanup()
        conversations.clear()

    def _dialogue_text(self, conversation_id: str) -> str:
        return (
            self.log_root
            / conversation_id
            / "dialogue.txt"
        ).read_text(encoding="utf-8")

    def test_telemetry_append_creates_log_file(self) -> None:
        conversation_id = "conversation-telemetry"

        append_telemetry_log(
            conversation_id=conversation_id,
            request_id="test-request",
            event_type="test",
            payload={"value": 1},
        )

        telemetry_path = (
            self.log_root
            / conversation_id
            / "telemetry.txt"
        )
        self.assertTrue(telemetry_path.exists())
        self.assertIn(
            '"event_type": "test"',
            telemetry_path.read_text(
                encoding="utf-8"
            ),
        )

    def test_completed_generation_is_corrected_to_heard_sentences(self) -> None:
        state = create_conversation()
        turn = add_dialogue_turn(
            state.conversation_id,
            request_id="request-a",
            user="Tell me about Queen Victoria.",
            assistant="A. B. C.",
        )

        updated = update_interrupted_assistant_response(
            state.conversation_id,
            "request-a",
            "A. [interrupted]",
        )

        self.assertIs(updated, turn)
        self.assertEqual(turn.assistant, "A. [interrupted]")

    def test_request_id_targets_earlier_turn_after_new_user_turn_arrives(self) -> None:
        state = create_conversation()
        first = add_dialogue_turn(
            state.conversation_id,
            request_id="request-a",
            user="Tell me about Queen Victoria.",
            assistant="A. B. C.",
        )
        second = add_dialogue_turn(
            state.conversation_id,
            request_id="request-b",
            user="by Thomas Sully.",
        )

        update_interrupted_assistant_response(
            state.conversation_id,
            "request-a",
            "A. [interrupted]",
        )

        self.assertEqual(first.assistant, "A. [interrupted]")
        self.assertEqual(second.user, "by Thomas Sully.")
        self.assertIsNone(second.assistant)

    def test_backend_cancellation_does_not_replace_playback_correction(self) -> None:
        state = create_conversation()
        turn = add_dialogue_turn(
            state.conversation_id,
            request_id="request-a",
            user="Tell me about Queen Victoria.",
            assistant="A. B. C.",
        )
        update_interrupted_assistant_response(
            state.conversation_id,
            "request-a",
            "A. [interrupted]",
        )

        mark_dialogue_turn_interrupted(
            state.conversation_id,
            turn,
        )

        self.assertEqual(turn.assistant, "A. [interrupted]")

    def test_rewritten_dialogue_removes_stale_complete_response(self) -> None:
        state = create_conversation()
        add_dialogue_turn(
            state.conversation_id,
            request_id="request-a",
            user="Tell me about Queen Victoria.",
            assistant="A. B. C.",
        )

        update_interrupted_assistant_response(
            state.conversation_id,
            "request-a",
            "A. [interrupted]",
        )

        content = self._dialogue_text(state.conversation_id)
        self.assertIn("Assistant:\nA. [interrupted]", content)
        self.assertNotIn("A. B. C.", content)

    def test_suppressed_turn_is_persisted_with_route_label(self) -> None:
        state = create_conversation()
        turn = add_dialogue_turn(
            state.conversation_id,
            request_id="request-noise",
            user="Mm-hm.",
        )

        update_dialogue_turn_context(
            state.conversation_id,
            turn,
            subject=[],
            reference=[],
            route_type="backchannel",
        )

        content = self._dialogue_text(state.conversation_id)
        self.assertIn("User [backchannel]:\nMm-hm.", content)
        self.assertIn("Assistant:\nNone", content)

    def test_rewrite_preserves_turn_creation_timestamp(self) -> None:
        state = create_conversation()
        turn = add_dialogue_turn(
            state.conversation_id,
            request_id="request-a",
            user="Tell me about Queen Victoria.",
            assistant="A. B. C.",
        )
        turn.created_at = datetime(
            2020,
            1,
            2,
            3,
            4,
            5,
            tzinfo=timezone.utc,
        )

        update_interrupted_assistant_response(
            state.conversation_id,
            "request-a",
            "A. [interrupted]",
        )

        content = self._dialogue_text(state.conversation_id)
        self.assertIn(
            "Timestamp: 2020-01-02T03:04:05+00:00",
            content,
        )

    def test_websocket_interruption_action_updates_existing_turn(self) -> None:
        state = create_conversation()
        turn = add_dialogue_turn(
            state.conversation_id,
            request_id="request-a",
            user="Tell me about Queen Victoria.",
            assistant="A. B. C.",
        )
        app = FastAPI()
        app.include_router(
            create_turn_buffer_stream_router()
        )

        with TestClient(app) as client:
            client.cookies.set(
                "conversation_id",
                state.conversation_id,
            )
            with client.websocket_connect(
                "/api/conversation/turn-buffer/stream"
            ) as websocket:
                ready = websocket.receive_json()
                websocket.send_json(
                    {
                        "type": (
                            "assistant_playback_interrupted"
                        ),
                        "request_id": "request-a",
                        "payload": {
                            "conversation_id": (
                                state.conversation_id
                            ),
                            "assistant_text": (
                                "A. [interrupted]"
                            ),
                        },
                    }
                )
                recorded = websocket.receive_json()

        self.assertEqual(ready["type"], "turn_stream_ready")
        self.assertEqual(
            recorded["type"],
            "assistant_playback_interruption_recorded",
        )
        self.assertTrue(recorded["payload"]["updated"])
        self.assertEqual(turn.assistant, "A. [interrupted]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
