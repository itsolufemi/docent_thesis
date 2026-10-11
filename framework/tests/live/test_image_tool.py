"""Generic load_image tests: filesystem safety, serialization and model replay."""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = FRAMEWORK_ROOT.parent
for root in (REPOSITORY_ROOT, FRAMEWORK_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from core_engine.schemas.tool_schemas import ToolCall, ToolExecutionContext
from core_engine.services.llm_service import stream_tool_aware_llm_response
from core_engine.tools.image_tool import create_image_tool
from core_engine.tools.tool_registry import ToolRegistry


JPEG = b"\xff\xd8\xff" + b"demo-test-image"


class ImageLoadingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "images-root"
        (self.root / "images").mkdir(parents=True)
        (self.root / "images" / "demo.jpg").write_bytes(JPEG)
        self.definition, self.handler = create_image_tool(image_root=self.root)
        self.registry = ToolRegistry()
        self.registry.register(self.definition, self.handler)

    def execute(self, reference: str):
        return self.registry.execute(
            ToolCall(name="load_image", arguments={"image_reference": reference}),
            ToolExecutionContext(conversation_id="test"),
        )

    def test_valid_image_is_returned_as_private_attachment(self) -> None:
        result = self.execute("images/demo.jpg")
        self.assertTrue(result.success)
        self.assertEqual(result.image_attachments[0].data, JPEG)
        self.assertEqual(result.image_attachments[0].media_type, "image/jpeg")
        self.assertEqual(result.data["image_reference"], "images/demo.jpg")

        # Neither returned JSON nor telemetry may contain the binary image.
        self.assertNotIn("image_attachments", result.model_dump(mode="json"))
        self.assertNotIn("image_attachments", result.model_dump_json())
        self.assertNotIn("image_attachments", result.model_payload())
        self.assertNotIn(base64.b64encode(JPEG).decode(), result.model_dump_json())

    def test_missing_image_returns_failed_result(self) -> None:
        result = self.execute("images/missing.jpg")
        self.assertFalse(result.success)
        self.assertEqual(result.image_attachments, [])

    def test_traversal_is_rejected(self) -> None:
        for name in ("../elsewhere.jpg", "/etc/hosts", r"C:\Windows\win.ini"):
            with self.subTest(name=name):
                self.assertFalse(self.execute(name).success)

    def test_file_type_and_size_are_checked(self) -> None:
        (self.root / "images" / "invalid.png").write_bytes(b"plain text")
        self.assertFalse(self.execute("images/invalid.png").success)
        definition, handler = create_image_tool(image_root=self.root, max_image_bytes=2)
        registry = ToolRegistry()
        registry.register(definition, handler)
        result = registry.execute(
            ToolCall(name="load_image", arguments={"image_reference": "images/demo.jpg"}),
            ToolExecutionContext(conversation_id="test"),
        )
        self.assertFalse(result.success)

    def test_streaming_tool_round_sends_actual_image_to_ollama(self) -> None:
        seen_messages = []
        def fake_stream(*, messages, **kwargs):
            seen_messages.append(json.loads(json.dumps(messages)))
            if len(seen_messages) == 1:
                yield {
                    "message": {
                        "tool_calls": [{
                            "function": {
                                "name": "load_image",
                                "arguments": {"image_reference": "images/demo.jpg"},
                            }
                        }]
                    },
                    "done": True,
                }
            else:
                yield {"message": {"content": "I can see the image."}, "done": True}

        with patch("core_engine.services.llm_service.stream_ollama_chat_request", side_effect=fake_stream):
            events = list(stream_tool_aware_llm_response(
                prompt="What is depicted?",
                conversation_id="test",
                buffer_for_tool_decision=True,
                tool_registry=self.registry,
            ))

        self.assertEqual(len(seen_messages), 2)
        followup = seen_messages[1][-1]
        self.assertEqual(followup["role"], "user")
        self.assertEqual(followup["images"], [base64.b64encode(JPEG).decode("ascii")])
        self.assertEqual(seen_messages[1][-2]["role"], "tool")
        self.assertNotIn("images", seen_messages[1][-2])
        self.assertEqual(
            [e.event_type for e in events if e.event_type == "response_complete"],
            ["response_complete"],
        )
        tool_results = [e.tool_result for e in events if e.event_type == "tool_result"]
        self.assertEqual(len(tool_results), 1)
        self.assertNotIn("image_attachments", tool_results[0])

    def test_docent_registers_image_tool(self) -> None:
        from apps.docent.tools import docent_tool_registry
        self.assertTrue(docent_tool_registry.has_tool("load_image"))
        self.assertTrue(docent_tool_registry.has_tool("retrieve_knowledge"))
        self.assertTrue(docent_tool_registry.has_tool("discover_docent_knowledge"))

    def test_docent_image_reference_instructions_prefer_evidence_then_fallback(self) -> None:
        from apps.docent.tools.image_tool import DOCENT_LOAD_IMAGE_TOOL

        definition = DOCENT_LOAD_IMAGE_TOOL
        self.assertIn("counting people", definition.description)
        self.assertIn("flowers", definition.description)
        self.assertIn("without redundant", definition.description)
        self.assertIn("images/N.jpg", definition.description)
        self.assertIn("NEVER 'painting:802'", definition.description)

        argument_description = definition.parameters["properties"][
            "image_reference"
        ]["description"]
        self.assertIn("image_reference", argument_description)
        self.assertIn("images/802.jpg", argument_description)
        self.assertIn("painting:802", argument_description)

    def test_image_reference_remains_a_file_path_not_a_painting_id(self) -> None:
        # We are deliberately *not* adding a resolver; this must remain invalid.
        self.assertFalse(self.execute("painting:802").success)

    def test_docent_visual_policy_and_discovery_policy_are_consistent(self) -> None:
        from apps.docent.services.docent_prompt_service import (
            DOCENT_CONTENT_GENERATION_RULES,
            DOCENT_DISCOVERY_POLICY_RULES,
        )
        from apps.docent.tools.discovery_tool import DOCENT_DISCOVERY_TOOL

        visual_rules = " ".join(DOCENT_CONTENT_GENERATION_RULES)
        discovery_rules = " ".join(DOCENT_DISCOVERY_POLICY_RULES)
        self.assertIn("successful load_image", visual_rules)
        self.assertIn("real time", visual_rules)
        self.assertIn("visual", discovery_rules)
        self.assertIn("visible detail", DOCENT_DISCOVERY_TOOL.description)


if __name__ == "__main__":
    unittest.main()
