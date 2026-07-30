from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from conversation_core.memory.conversation_store import (  # noqa: E402
    create_conversation,
)
from conversation_core.services.classifier_tool_orchestration_service import (  # noqa: E402
    run_required_classifier_tool_round,
)


CHECKPOINT_CASES = [
    {
        "text": (
            "Tell me about The Arab Tent."
        ),
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
    },
    {
        "text": "Hi, how are you?",
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
    },
    {
        "text": (
            "Start a highlights tour."
        ),
        "route_type": "call_to_action",
        "requires_retrieval": True,
        "proposed_action": (
            "create_bounded_branch"
        ),
    },
]


def main() -> None:
    conversation = create_conversation()
    results = []

    for case in CHECKPOINT_CASES:
        result = (
            run_required_classifier_tool_round(
                text=case["text"],
                conversation_id=(
                    conversation
                    .conversation_id
                ),
            )
        )
        route = result.utterance_route
        correct = (
            route.route_type
            == case["route_type"]
            and route.requires_retrieval
            == case["requires_retrieval"]
            and route.proposed_action
            == case["proposed_action"]
            and (
                result.audit
                .classifier_called_exactly_once
            )
            and not (
                result.audit
                .invalid_classifier_arguments
            )
        )
        row = {
            "text": case["text"],
            "correct": correct,
            "route": route.model_dump(
                mode="json"
            ),
            "audit": result.audit.model_dump(
                mode="json"
            ),
        }
        results.append(row)
        print(
            json.dumps(row, indent=2),
            flush=True,
        )

    if not all(
        result["correct"]
        for result in results
    ):
        raise AssertionError(
            "At least one classifier-tool "
            "checkpoint case failed."
        )

    output_path = (
        BACKEND_ROOT
        / "tmp"
        / "latency"
        / "classifier_tool_checkpoint.json"
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(
            {
                "case_count": len(results),
                "all_correct": True,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Report: {output_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
