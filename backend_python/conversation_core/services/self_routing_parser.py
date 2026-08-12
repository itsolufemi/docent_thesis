from __future__ import annotations

import json

from pydantic import ValidationError

from conversation_core.schemas.self_routing_schemas import (
    SelfRoutingAssessment,
)


OPENING_TAG = "<route>"
CLOSING_TAG = "</route>"


class SelfRoutingStreamParser:
    """
    Stream visitor-facing response text immediately while buffering the
    final self-routing footer.

    Expected response shape:

        Visitor-facing response.

        <route>{...}</route>

    For ignored utterances, the model should return only the route footer
    and no visitor-facing text.
    """

    def __init__(self) -> None:
        self._buffer = ""

        self.route: SelfRoutingAssessment | None = None

        self.route_started = False
        self.route_complete = False
        self.route_just_completed = False

        self.validation_error: str | None = None

    def consume(
        self,
        text: str,
    ) -> str:
        """
        Return only text that is safe to expose to the visitor.

        Once <route> begins, all subsequent text is buffered and never
        released as spoken content.
        """
        self.route_just_completed = False

        if not text:
            return ""

        if self.route_complete:
            if text.strip():
                self.validation_error = (
                    self.validation_error
                    or (
                        "The response contained text after "
                        "the self-routing footer."
                    )
                )
            return ""

        self._buffer += text

        if self.route_started:
            self._try_complete_route()
            return ""

        opening_index = self._buffer.find(
            OPENING_TAG
        )

        if opening_index >= 0:
            spoken_text = self._buffer[
                :opening_index
            ]
            self._buffer = self._buffer[
                opening_index:
            ]
            self.route_started = True
            self._try_complete_route()

            return spoken_text

        # The opening tag may be split across streamed chunks. Keep only
        # the longest suffix that could still become the opening tag.
        suffix_length = self._partial_opening_tag_length(
            self._buffer
        )

        if suffix_length:
            spoken_text = self._buffer[
                :-suffix_length
            ]
            self._buffer = self._buffer[
                -suffix_length:
            ]
            return spoken_text

        spoken_text = self._buffer
        self._buffer = ""
        return spoken_text

    def finish(self) -> str:
        """
        Finish parsing when the model stream ends.

        Any ordinary text still buffered is visitor-facing text. An
        incomplete route footer is discarded and reported as invalid.
        """
        self.route_just_completed = False

        if self.route_complete:
            return ""

        if self.route_started:
            self.validation_error = (
                self.validation_error
                or (
                    "The self-routing footer was not "
                    "closed."
                )
            )
            self._buffer = ""
            return ""

        pending = self._buffer
        self._buffer = ""

        if pending and OPENING_TAG.startswith(pending):
            self.validation_error = (
                "The self-routing footer was not "
                "closed."
            )
            return ""

        self.validation_error = (
            "The response ended without a "
            "self-routing footer."
        )

        return pending

    def cancel(self) -> None:
        """
        Discard an unfinished footer without treating cancellation as a
        response-format failure.
        """
        self._buffer = ""
        self.route_just_completed = False

    def _try_complete_route(self) -> None:
        if CLOSING_TAG not in self._buffer:
            return

        route_part, trailing_text = (
            self._buffer.split(
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

        if trailing_text.strip():
            trailing_error = (
                "The response contained text after "
                "the self-routing footer."
            )

            if self.validation_error:
                self.validation_error = (
                    f"{self.validation_error}; "
                    f"{trailing_error}"
                )
            else:
                self.validation_error = (
                    trailing_error
                )

        self._buffer = ""
        self.route_complete = True
        self.route_just_completed = True

    @staticmethod
    def _partial_opening_tag_length(
        text: str,
    ) -> int:
        """
        Return the length of the longest suffix of `text` that is also a
        prefix of "<route>".
        """
        maximum = min(
            len(text),
            len(OPENING_TAG) - 1,
        )

        for length in range(
            maximum,
            0,
            -1,
        ):
            if text.endswith(
                OPENING_TAG[:length]
            ):
                return length

        return 0
