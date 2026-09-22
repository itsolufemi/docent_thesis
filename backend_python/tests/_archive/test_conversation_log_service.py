from __future__ import annotations

import json
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch


BACKEND_PYTHON_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_PYTHON_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_PYTHON_ROOT),
    )


from conversation_core.schemas.conversation_schemas import (
    DialogueTurn,
)
from conversation_core.services.conversation_log_service import (
    append_dialogue_turn_log,
    append_telemetry_log,
)


class ConversationLogServiceTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.log_root = Path(
            self.temporary_directory.name
        )

        self.directory_patch = patch(
            (
                "conversation_core.services."
                "conversation_log_service.settings."
                "conversation_log_directory"
            ),
            self.log_root,
        )

        self.enabled_patch = patch(
            (
                "conversation_core.services."
                "conversation_log_service.settings."
                "conversation_logging_enabled"
            ),
            True,
        )

        self.directory_patch.start()
        self.enabled_patch.start()

    def tearDown(self) -> None:
        self.enabled_patch.stop()
        self.directory_patch.stop()
        self.temporary_directory.cleanup()

    def test_dialogue_log_contains_turn_text(
        self,
    ) -> None:
        turn = DialogueTurn(
            role="user",
            content="Tell me about The Swing.",
        )

        append_dialogue_turn_log(
            conversation_id=(
                "conversation-123"
            ),
            turn=turn,
        )

        dialogue_path = (
            self.log_root
            / "conversation-123"
            / "dialogue.txt"
        )

        self.assertTrue(
            dialogue_path.exists()
        )

        content = dialogue_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Role: user",
            content,
        )
        self.assertIn(
            "Tell me about The Swing.",
            content,
        )

    def test_dialogue_log_contains_subject_state(
        self,
    ) -> None:
        turn = DialogueTurn(
            role="assistant",
            content=(
                "The painting is by Fragonard."
            ),
            previous_subject="The Arab Tent",
            current_subject="The Swing",
            current_subject_reference=(
                "painting:123"
            ),
        )

        append_dialogue_turn_log(
            conversation_id=(
                "conversation-subject"
            ),
            turn=turn,
        )

        dialogue_path = (
            self.log_root
            / "conversation-subject"
            / "dialogue.txt"
        )

        content = dialogue_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "Previous subject: "
                "The Arab Tent"
            ),
            content,
        )
        self.assertIn(
            "Current subject: The Swing",
            content,
        )
        self.assertIn(
            (
                "Subject reference: "
                "painting:123"
            ),
            content,
        )

    def test_telemetry_log_appends_multiple_events(
        self,
    ) -> None:
        append_telemetry_log(
            conversation_id=(
                "conversation-telemetry"
            ),
            request_id="request-1",
            event_type=(
                "backend_turn_complete"
            ),
            payload={
                "queryToFirstDeltaSeconds": (
                    0.82
                ),
            },
        )

        append_telemetry_log(
            conversation_id=(
                "conversation-telemetry"
            ),
            request_id="request-1",
            event_type=(
                "client_voice_telemetry"
            ),
            payload={
                "queryToPlaybackSeconds": (
                    1.40
                ),
            },
        )

        telemetry_path = (
            self.log_root
            / "conversation-telemetry"
            / "telemetry.txt"
        )

        content = telemetry_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '"event_type": '
            '"backend_turn_complete"',
            content,
        )
        self.assertIn(
            '"event_type": '
            '"client_voice_telemetry"',
            content,
        )
        self.assertIn(
            '"request_id": "request-1"',
            content,
        )

        first_position = content.index(
            "backend_turn_complete"
        )
        second_position = content.index(
            "client_voice_telemetry"
        )

        self.assertLess(
            first_position,
            second_position,
        )

    def test_separate_conversations_use_separate_directories(
        self,
    ) -> None:
        turn = DialogueTurn(
            role="user",
            content="Hello.",
        )

        append_dialogue_turn_log(
            conversation_id="conversation-a",
            turn=turn,
        )

        append_dialogue_turn_log(
            conversation_id="conversation-b",
            turn=turn,
        )

        path_a = (
            self.log_root
            / "conversation-a"
            / "dialogue.txt"
        )
        path_b = (
            self.log_root
            / "conversation-b"
            / "dialogue.txt"
        )

        self.assertTrue(path_a.exists())
        self.assertTrue(path_b.exists())
        self.assertNotEqual(
            path_a.parent,
            path_b.parent,
        )

    def test_logging_can_be_disabled(
        self,
    ) -> None:
        with patch(
            (
                "conversation_core.services."
                "conversation_log_service.settings."
                "conversation_logging_enabled"
            ),
            False,
        ):
            append_dialogue_turn_log(
                conversation_id=(
                    "disabled-conversation"
                ),
                turn=DialogueTurn(
                    role="user",
                    content="Do not log this.",
                ),
            )

            append_telemetry_log(
                conversation_id=(
                    "disabled-conversation"
                ),
                request_id="request-disabled",
                event_type="test",
                payload={},
            )

        conversation_directory = (
            self.log_root
            / "disabled-conversation"
        )

        self.assertFalse(
            conversation_directory.exists()
        )

    def test_conversation_id_cannot_escape_log_directory(
        self,
    ) -> None:
        append_dialogue_turn_log(
            conversation_id=(
                "../../outside-folder"
            ),
            turn=DialogueTurn(
                role="user",
                content="Safe content.",
            ),
        )

        escaped_path = (
            self.log_root.parent
            / "outside-folder"
        )

        self.assertFalse(
            escaped_path.exists()
        )

        created_directories = [
            path
            for path in self.log_root.iterdir()
            if path.is_dir()
        ]

        self.assertEqual(
            len(created_directories),
            1,
        )

        created_directory = (
            created_directories[0]
        )

        self.assertEqual(
            created_directory.parent,
            self.log_root,
        )

        self.assertTrue(
            (
                created_directory
                / "dialogue.txt"
            ).exists()
        )

    def test_telemetry_records_are_valid_json_objects(
        self,
    ) -> None:
        append_telemetry_log(
            conversation_id=(
                "conversation-json"
            ),
            request_id="request-json",
            event_type="test_event",
            payload={
                "seconds": 1.25,
                "successful": True,
            },
        )

        telemetry_path = (
            self.log_root
            / "conversation-json"
            / "telemetry.txt"
        )

        content = telemetry_path.read_text(
            encoding="utf-8"
        ).strip()

        parsed = json.loads(content)

        self.assertEqual(
            parsed["conversation_id"],
            "conversation-json",
        )
        self.assertEqual(
            parsed["request_id"],
            "request-json",
        )
        self.assertEqual(
            parsed["event_type"],
            "test_event",
        )
        self.assertEqual(
            parsed["payload"]["seconds"],
            1.25,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)