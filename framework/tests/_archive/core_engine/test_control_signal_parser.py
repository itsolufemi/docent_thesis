from __future__ import annotations

import unittest

from core_engine.services.control_signal_parser import (
    ControlSignalStreamParser,
)


class ControlSignalStreamParserTest(unittest.TestCase):
    def test_normal_text_streams_immediately(self) -> None:
        parser = ControlSignalStreamParser()

        self.assertEqual(parser.consume("The Swing was"), "The Swing was")
        self.assertEqual(parser.consume(" painted by Fragonard."), " painted by Fragonard.")
        self.assertEqual(parser.finish(), "")
        self.assertIsNone(parser.control_signal)

    def test_backchannel_is_suppressed(self) -> None:
        parser = ControlSignalStreamParser()

        spoken = parser.consume(
            '<control>{"route_type":"backchannel"}</control>'
        )

        self.assertEqual(spoken, "")
        self.assertEqual(parser.control_signal.route_type, "backchannel")

    def test_potential_noise_is_suppressed(self) -> None:
        parser = ControlSignalStreamParser()

        parser.consume(
            '<control>{"route_type":"potential_noise"}</control>'
        )

        self.assertEqual(
            parser.control_signal.route_type,
            "potential_noise",
        )

    def test_interruption_is_suppressed(self) -> None:
        parser = ControlSignalStreamParser()

        parser.consume(
            '<control>{"route_type":"interruption"}</control>'
        )

        self.assertEqual(
            parser.control_signal.route_type,
            "interruption",
        )

    def test_opening_tag_can_be_split_across_chunks(self) -> None:
        parser = ControlSignalStreamParser()

        parts = [
            "<con",
            "trol>",
            '{"route_type":"backchannel"}',
            "</control>",
        ]

        self.assertEqual(
            "".join(parser.consume(part) for part in parts),
            "",
        )
        self.assertEqual(parser.control_signal.route_type, "backchannel")

    def test_json_can_be_split_across_chunks(self) -> None:
        parser = ControlSignalStreamParser()

        self.assertEqual(
            parser.consume('<control>{"route_'),
            "",
        )
        self.assertEqual(
            parser.consume('type":"interruption"}</control>'),
            "",
        )
        self.assertEqual(
            parser.control_signal.route_type,
            "interruption",
        )

    def test_malformed_control_is_discarded_and_reported(self) -> None:
        parser = ControlSignalStreamParser()

        spoken = parser.consume(
            '<control>{"route_type":"unknown"}</control>'
        )

        self.assertEqual(spoken, "")
        self.assertIsNone(parser.control_signal)
        self.assertIsNotNone(parser.validation_error)

    def test_normal_text_beginning_with_angle_bracket_is_released(self) -> None:
        parser = ControlSignalStreamParser()

        self.assertEqual(parser.consume("<hello>"), "<hello>")

    def test_normal_response_may_contain_json_later(self) -> None:
        parser = ControlSignalStreamParser()

        first = parser.consume("Here is the result: ")
        second = parser.consume('{"route_type":"backchannel"}')

        self.assertEqual(
            first + second,
            'Here is the result: {"route_type":"backchannel"}',
        )
        self.assertIsNone(parser.control_signal)

    def test_incomplete_control_is_discarded_on_finish(self) -> None:
        parser = ControlSignalStreamParser()

        self.assertEqual(parser.consume("<control>"), "")
        self.assertEqual(parser.finish(), "")
        self.assertIsNotNone(parser.validation_error)


if __name__ == "__main__":
    unittest.main()
