from __future__ import annotations

import json

from pydantic import ValidationError

from core_engine.schemas.control_signal_schemas import (
    ControlSignal,
)


OPENING_TAG = "<control>"
CLOSING_TAG = "</control>"


class ControlSignalStreamParser:
    """Suppress exceptional controls while immediately releasing speech."""

    def __init__(self) -> None:
        self._buffer = ""
        self._ordinary_response: bool | None = None

        self.control_signal: ControlSignal | None = None
        self.control_just_completed = False
        self.validation_error: str | None = None

    def consume(self, text: str) -> str:
        self.control_just_completed = False

        if not text:
            return ""

        if self._ordinary_response is True:
            return text

        if self._ordinary_response is False:
            if text.strip():
                self.validation_error = (
                    self.validation_error
                    or "The response contained text after the control signal."
                )
            return ""

        self._buffer += text
        stripped = self._buffer.lstrip()

        if stripped.startswith(OPENING_TAG):
            if CLOSING_TAG not in stripped:
                return ""

            payload_part, trailing_text = stripped.split(
                CLOSING_TAG,
                1,
            )
            payload_text = payload_part.removeprefix(
                OPENING_TAG
            ).strip()

            try:
                self.control_signal = ControlSignal.model_validate(
                    json.loads(payload_text)
                )
            except (
                json.JSONDecodeError,
                ValidationError,
                ValueError,
            ) as error:
                self.validation_error = str(error)

            if trailing_text.strip():
                trailing_error = (
                    "The response contained text after the control signal."
                )
                self.validation_error = (
                    f"{self.validation_error}; {trailing_error}"
                    if self.validation_error
                    else trailing_error
                )

            self._buffer = ""
            self._ordinary_response = False
            self.control_just_completed = True
            return ""

        if OPENING_TAG.startswith(stripped):
            return ""

        self._ordinary_response = True
        ordinary_text = self._buffer
        self._buffer = ""
        return ordinary_text

    def finish(self) -> str:
        self.control_just_completed = False

        if self._ordinary_response is not None:
            return ""

        pending = self._buffer
        self._buffer = ""

        if not pending:
            return ""

        stripped = pending.lstrip()

        if (
            stripped.startswith(OPENING_TAG)
            or OPENING_TAG.startswith(stripped)
        ):
            self._ordinary_response = False
            self.validation_error = (
                "The control signal was not closed."
            )
            return ""

        self._ordinary_response = True
        return pending
