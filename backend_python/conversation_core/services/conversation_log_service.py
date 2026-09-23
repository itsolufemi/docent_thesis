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
    if not settings.conversation_logging_enabled:
        return False


def _dialogue_turn_entry(
    turn: DialogueTurn,
) -> str:
    route_labels = {
        "potential_noise": "potential noise",
        "backchannel": "backchannel",
        "interruption": "interruption",
    }
    route_label = route_labels.get(
        turn.route_type
    )
    user_label = (
        f"User [{route_label}]"
        if route_label
        else "User"
    )

    return "\n".join(
        [
            "",
            "========================================",
            f"Timestamp: {_utc_timestamp()}",
            f"Request ID: {turn.request_id or 'None'}",
            f"Previous subjects: {turn.previous_subject}",
            f"Subjects: {turn.subject}",
            f"References: {turn.reference}",
            f"{user_label}:",
            turn.user or "None",
            "Assistant:",
            turn.assistant or "None",
            "========================================",
            "",
        ]
    )

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
    """Append one complete user-assistant exchange."""
    if not settings.conversation_logging_enabled:
        return

    directory = _conversation_directory(
        conversation_id
    )

    entry = _dialogue_turn_entry(turn)

    _append_text(
        directory / "dialogue.txt",
        entry,
    )


def rewrite_dialogue_log(
    *,
    conversation_id: str,
    dialogue_history: list[DialogueTurn],
) -> None:
    """Replace dialogue.txt with the current canonical in-memory history."""
    if not settings.conversation_logging_enabled:
        return

    directory = _conversation_directory(
        conversation_id
    )
    path = directory / "dialogue.txt"
    temporary_path = directory / "dialogue.txt.tmp"
    content = "".join(
        _dialogue_turn_entry(turn)
        for turn in dialogue_history
    )

    try:
        with _file_lock:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )
            temporary_path.write_text(
                content,
                encoding="utf-8",
                newline="\n",
            )
            temporary_path.replace(path)
    except OSError as error:
        print(
            f"Conversation logging failed for "
            f"{path}: {error}"
        )


def append_telemetry_log(
    *,
    conversation_id: str,
    request_id: str | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    if not settings.conversation_logging_enabled:
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
