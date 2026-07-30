from __future__ import annotations

import json

from pydantic import ValidationError

from conversation_core.schemas.self_routing_schemas import (
    SelfRoutingAssessment,
)


OPENING_TAG = "<route>"
CLOSING_TAG = "</route>"


class SelfRoutingStreamParser:
    def __init__(self) -> None:
        self._buffer = ""
        self.route: (
            SelfRoutingAssessment | None
        ) = None
        self.route_complete = False
        self.route_just_completed = False
        self.validation_error: str | None = None

    def consume(
        self,
        text: str,
    ) -> str:
        self.route_just_completed = False

        if not text:
            return ""

        if self.route_complete:
            return text

        self._buffer += text
        candidate = self._buffer.lstrip()

        if not (
            candidate.startswith(OPENING_TAG)
            or OPENING_TAG.startswith(candidate)
        ):
            spoken_text = self._buffer
            self._buffer = ""
            self.route_complete = True
            self.route_just_completed = True
            self.validation_error = (
                "The response did not begin with "
                "a self-routing block."
            )
            return spoken_text

        if CLOSING_TAG not in candidate:
            return ""

        route_part, remaining_text = (
            candidate.split(
                CLOSING_TAG,
                1,
            )
        )
        route_json = route_part.replace(
            OPENING_TAG,
            "",
            1,
        ).strip()

        try:
            payload = json.loads(route_json)
            self.route = (
                SelfRoutingAssessment
                .model_validate(payload)
            )
        except (
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ) as error:
            self.route = None
            self.validation_error = str(error)

        self.route_complete = True
        self.route_just_completed = True
        self._buffer = ""
        return remaining_text

    def finish(self) -> str:
        self.route_just_completed = False

        if self.route_complete:
            return ""

        pending = self._buffer
        self._buffer = ""
        self.route_complete = True
        self.route_just_completed = True
        candidate = pending.lstrip()

        if not candidate.startswith(
            OPENING_TAG
        ):
            self.validation_error = (
                "The response ended without a "
                "self-routing block."
            )
            return pending

        self.validation_error = (
            "The self-routing block was not "
            "closed."
        )
        route_payload = candidate[
            len(OPENING_TAG):
        ].lstrip()

        try:
            _, end_index = (
                json.JSONDecoder().raw_decode(
                    route_payload
                )
            )
        except json.JSONDecodeError:
            line_break = route_payload.find(
                "\n"
            )

            if line_break < 0:
                return ""

            return route_payload[
                line_break + 1:
            ]

        return route_payload[end_index:].lstrip()
