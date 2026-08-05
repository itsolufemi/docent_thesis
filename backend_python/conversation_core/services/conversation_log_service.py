from __future__ import annotations

import json

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from config import settings
from conversation_core.schemas.conversation_schemas import (
    DialogueTurn,
)


_file_lock = RLock()


def _utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _safe_conversation_id(
    conversation_id: str,
) -> str:
    """
    Prevent conversation identifiers from becoming arbitrary paths.
    """
    return "".join(
        character
        for character in conversation_id
        if (
            character.isalnum()
            or character in {"-", "_"}
        )
    )


def _conversation_directory(
    conversation_id: str,
) -> Path:
    safe_id = _safe_conversation_id(
        conversation_id
    )

    if not safe_id:
        raise ValueError(
            "Conversation ID cannot be empty."
        )

    root = Path(
        settings.conversation_log_directory
    )

    return root / safe_id


def _append_text(
    path: Path,
    content: str,
) -> bool:
    if not (
        settings.conversation_logging_enabled
    ):
        return False

    try:
        with _file_lock:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            ) as file:
                file.write(content)
                file.flush()

        return True
    except OSError as error:
        print(
            f"Conversation logging failed for "
            f"{path}: {error}"
        )
        return False


def append_dialogue_turn_log(
    *,
    conversation_id: str,
    turn: DialogueTurn,
) -> None:
    """
    Append one human-readable dialogue turn.
    """
    if not (
        settings.conversation_logging_enabled
    ):
        return

    directory = _conversation_directory(
        conversation_id
    )

    role = (
        turn.role.value
        if hasattr(turn.role, "value")
        else str(turn.role)
    )

    subject_lines = [
        (
            "Previous subject: "
            f"{turn.previous_subject or 'None'}"
        ),
        (
            "Current subject: "
            f"{turn.current_subject or 'None'}"
        ),
        (
            "Subject reference: "
            f"{turn.current_subject_reference or 'None'}"
        ),
    ]

    entry = "\n".join(
        [
            "",
            (
                "========================================"
            ),
            f"Timestamp: {_utc_timestamp()}",
            f"Role: {role}",
            *subject_lines,
            "Text:",
            turn.content,
            (
                "========================================"
            ),
            "",
        ]
    )

    _append_text(
        directory / "dialogue.txt",
        entry,
    )


def append_telemetry_log(
    *,
    conversation_id: str,
    request_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """
    Append one structured telemetry event.

    The file remains a .txt file, but each event is formatted JSON so
    that it is both readable and machine-parseable.
    """
    if not (
        settings.conversation_logging_enabled
    ):
        return

    directory = _conversation_directory(
        conversation_id
    )

    record = {
        "timestamp": _utc_timestamp(),
        "conversation_id": conversation_id,
        "request_id": request_id,
        "event_type": event_type,
        "payload": payload,
    }

    entry = (
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n\n"
    )

    _append_text(
        directory / "telemetry.txt",
        entry,
    )
