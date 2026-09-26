from __future__ import annotations

import unittest

from conversation_core.schemas.source_schemas import (
    QuerySource,
)
from conversation_core.schemas.tool_schemas import (
    ToolDialogueStateUpdate,
    ToolExecutionResult,
)


class ToolDialogueStateTest(unittest.TestCase):
    def test_tool_result_carries_generic_state_and_sources(self) -> None:
        result = ToolExecutionResult(
            tool_name="retrieve_knowledge",
            success=True,
            message="Retrieved knowledge.",
            dialogue_state=ToolDialogueStateUpdate(
                subjects=["Subject A"],
                references=["record:1"],
            ),
            sources=[
                QuerySource(
                    source_type="retrieved_chunk",
                    title="Subject A",
                    reference="record:1",
                )
            ],
        )

        payload = result.model_dump(mode="json")

        self.assertEqual(
            payload["dialogue_state"],
            {
                "subjects": ["Subject A"],
                "references": ["record:1"],
            },
        )
        self.assertEqual(
            payload["sources"][0]["reference"],
            "record:1",
        )

    def test_existing_tool_results_default_to_no_state(self) -> None:
        result = ToolExecutionResult(
            tool_name="plain_tool",
            success=True,
            message="Done.",
        )

        self.assertIsNone(result.dialogue_state)
        self.assertEqual(result.sources, [])


if __name__ == "__main__":
    unittest.main()
