from __future__ import annotations

import sys
import unittest

from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    conversations,
    create_conversation,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.services.query_service import (  # noqa: E402
    QueryEngine,
)
from docent.services.docent_query_service import (  # noqa: E402
    docent_build_direct_prompt,
)
from docent.tools import docent_tool_registry  # noqa: E402


class DirectQueryEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        conversations.clear()
        self.state = create_conversation()

    def tearDown(self) -> None:
        conversations.clear()

    def _engine(self) -> QueryEngine:
        return QueryEngine(
            subject_resolver=None,
            prompt_builder=docent_build_direct_prompt,
            direct_routing_enabled=True,
            tool_registry=docent_tool_registry,
        )

    @patch(
        "conversation_core.services.query_service."
        "stream_direct_routed_response"
    )
    def test_normal_response_skips_subject_resolver(self, stream) -> None:
        stream.return_value = iter(
            [
                LLMStreamEvent(event_type="response_started"),
                LLMStreamEvent(
                    event_type="content_delta",
                    text="Hello there.",
                ),
                LLMStreamEvent(
                    event_type="response_complete",
                    text="Hello there.",
                    done=True,
                ),
            ]
        )

        result = self._engine().generate_streaming_response(
            "Hello.",
            conversation_id=self.state.conversation_id,
            include_debug=True,
        )

        self.assertEqual(result.response, "Hello there.")
        self.assertEqual(
            result.debug.context_source,
            "direct_routing",
        )
        self.assertEqual(
            self.state.dialogue_history[-1].assistant,
            "Hello there.",
        )
        stream.assert_called_once()
        self.assertIs(
            stream.call_args.kwargs["tool_registry"],
            docent_tool_registry,
        )

    def test_non_direct_engine_still_requires_resolver(self) -> None:
        with self.assertRaises(ValueError):
            QueryEngine(
                subject_resolver=None,
                prompt_builder=docent_build_direct_prompt,
            )


if __name__ == "__main__":
    unittest.main()
