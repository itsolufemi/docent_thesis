from __future__ import annotations

import json

from pydantic import ValidationError

from conversation_core.schemas.model_route_schemas import (
    ModelRouteAssessment,
)


ROUTE_OPEN_TAG = "<route>"
ROUTE_CLOSE_TAG = "</route>"


class ModelRouteStreamParser:
    def __init__(self) -> None:
        self.buffer = ""
        self.route_complete = False
        self.route_boundary_reached = False
        self.route: ModelRouteAssessment | None = None
        self.validation_error: str | None = None

    def consume(
        self,
        text: str,
    ) -> tuple[
        ModelRouteAssessment | None,
        str,
    ]:
        if not text:
            return None, ""

        if self.route_complete:
            return None, text

        self.buffer += text
        candidate = self.buffer.lstrip()

        if not (
            candidate.startswith(ROUTE_OPEN_TAG)
            or ROUTE_OPEN_TAG.startswith(candidate)
        ):
            spoken_text = self.buffer
            self.buffer = ""
            self.route_complete = True
            self.validation_error = (
                "The response did not begin with "
                "a route block."
            )
            return None, spoken_text

        close_index = candidate.find(
            ROUTE_CLOSE_TAG
        )

        if close_index < 0:
            return None, ""

        route_json = candidate[
            len(ROUTE_OPEN_TAG):close_index
        ].strip()
        spoken_text = candidate[
            close_index + len(ROUTE_CLOSE_TAG):
        ]

        self.buffer = ""
        self.route_complete = True
        self.route_boundary_reached = True

        try:
            self.route = (
                ModelRouteAssessment
                .model_validate_json(route_json)
            )
        except (
            ValidationError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            self.validation_error = str(error)
            self.route = None

        return self.route, spoken_text

    def finish(self) -> str:
        if self.route_complete:
            return ""

        pending = self.buffer
        self.buffer = ""
        self.route_complete = True

        candidate = pending.lstrip()

        if not candidate.startswith(
            ROUTE_OPEN_TAG
        ):
            self.validation_error = (
                "The response ended without a "
                "route block."
            )
            return pending

        self.validation_error = (
            "The route block was not closed."
        )
        route_payload = candidate[
            len(ROUTE_OPEN_TAG):
        ].lstrip()

        try:
            _, end_index = (
                json.JSONDecoder().raw_decode(
                    route_payload
                )
            )
        except json.JSONDecodeError:
            first_line_break = (
                route_payload.find("\n")
            )

            if first_line_break < 0:
                return ""

            return route_payload[
                first_line_break + 1:
            ]

        return route_payload[end_index:].lstrip()
