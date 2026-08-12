from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from config import settings  # noqa: E402
from conversation_core.memory.conversation_store import (  # noqa: E402
    add_dialogue_turn,
    create_conversation,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from docent.services.docent_query_service import (  # noqa: E402
    self_routing_docent_query_engine,
)


CASES = [
    {
        "case_id": "artwork_information",
        "text": (
            "Tell me about The Arab Tent."
        ),
        "route_type": "response_request",
        "is_relevant": True,
        "retrieval_used": True,
        "candidate_subjects": [
            "painting:581"
        ],
        "expected_tool": None,
    },
    {
        "case_id": "greeting",
        "text": "Hi, how are you?",
        "route_type": "response_request",
        "is_relevant": True,
        "retrieval_used": False,
        "candidate_subjects": None,
        "expected_tool": None,
    },
    {
        "case_id": "current_subject",
        "text": "What painting is this?",
        "route_type": "response_request",
        "is_relevant": True,
        "retrieval_used": True,
        "candidate_subjects": ["The Arab Tent"],
        "expected_tool": None,
        "current_subject_reference": "painting:581",
        "current_subject_label": "The Arab Tent",
    },
    {
        "case_id": "highlights_tour",
        "text": (
            "Start a highlights tour."
        ),
        "route_type": "call_to_action",
        "is_relevant": True,
        "retrieval_used": True,
        "candidate_subjects": None,
        "expected_tool": (
            "create_conversation_branch"
        ),
    },
    {
        "case_id": "noise",
        "text": (
            "[unintelligible background noise]"
        ),
        "route_type": "noise",
        "is_relevant": False,
        "retrieval_used": False,
        "candidate_subjects": None,
        "expected_tool": None,
    },
]


def median(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return round(
        statistics.median(values),
        4,
    )


def run_sample(
    *,
    case: dict,
    repetition: int,
) -> dict:
    conversation = create_conversation()
    conversation_id = (
        conversation.conversation_id
    )
    current_subject_reference = case.get(
        "current_subject_reference"
    )

    if current_subject_reference is not None:
        add_dialogue_turn(
            conversation_id=conversation_id,
            role="assistant",
            content="Previous subject context.",
            current_subject=case.get(
                "current_subject_label"
            ),
            current_subject_reference=(
                current_subject_reference
            ),
        )

    started_at = perf_counter()
    self_routing_time = None
    first_spoken_time = None
    assessment = None
    tool_calls: list[str] = []
    tool_results: list[dict] = []
    event_types: list[str] = []

    def handle_event(
        event: LLMStreamEvent,
    ) -> None:
        nonlocal self_routing_time
        nonlocal first_spoken_time
        nonlocal assessment

        event_types.append(event.event_type)
        elapsed = perf_counter() - started_at

        if event.event_type == "self_routing":
            self_routing_time = elapsed
            assessment = event.route_assessment

        if (
            event.event_type
            == "content_delta"
            and event.text
            and first_spoken_time is None
        ):
            first_spoken_time = elapsed

        if event.event_type == "tool_call":
            tool_calls.extend(
                str(call.get("name", ""))
                for call in event.tool_calls
            )

        if event.event_type == "tool_result":
            tool_results.append(
                event.tool_result or {}
            )

    try:
        result = (
            self_routing_docent_query_engine
            .generate_streaming_response(
                text=case["text"],
                conversation_id=conversation_id,
                include_debug=True,
                on_stream_event=handle_event,
            )
        )
        total_time = perf_counter() - started_at
        debug_payload = (
            result.debug.debug_payload
            if result.debug is not None
            else {}
        )
        assessment = (
            assessment
            or debug_payload.get(
                "self_routing"
            )
        )
        route_valid = bool(
            debug_payload.get(
                "self_routing_valid"
            )
        )
        retrieval_available = bool(
            result.sources
        )
        expected_tool = case[
            "expected_tool"
        ]
        matching_tool_results = [
            tool_result
            for tool_result in tool_results
            if (
                tool_result.get("tool_name")
                == expected_tool
            )
        ]
        tool_correct = (
            not tool_calls
            if expected_tool is None
            else (
                expected_tool in tool_calls
                and bool(
                    matching_tool_results
                )
                and all(
                    item.get("success") is True
                    for item
                    in matching_tool_results
                )
            )
        )
        route_correct = (
            assessment is not None
            and assessment["route_type"]
            == case["route_type"]
            and assessment["should_ignore"]
            == case["should_ignore"]
        )
        retrieval_available_correct = (
            assessment is not None
            and assessment[
                "retrieval_available"
            ]
            == retrieval_available
        )
        retrieval_used_correct = (
            assessment is not None
            and assessment["retrieval_used"]
            == case["retrieval_used"]
        )
        candidate_subjects_correct = (
            assessment is not None
            and assessment.get(
                "candidate_subjects"
            )
            == case["candidate_subjects"]
        )
        proposed_action_correct = (
            assessment is not None
            and bool(
                assessment.get(
                    "proposed_action"
                )
            )
            == (expected_tool is not None)
        )
        timings = debug_payload.get(
            "timings",
            {},
        )

        return {
            "success": True,
            "case_id": case["case_id"],
            "text": case["text"],
            "repetition": repetition,
            "assessment": assessment,
            "route_valid": route_valid,
            "route_correct": route_correct,
            "retrieval_available_correct": (
                retrieval_available_correct
            ),
            "retrieval_used_correct": (
                retrieval_used_correct
            ),
            "candidate_subjects_correct": (
                candidate_subjects_correct
            ),
            "proposed_action_correct": (
                proposed_action_correct
            ),
            "tool_correct": tool_correct,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "retrieval_available_actual": (
                retrieval_available
            ),
            "sources_count": len(
                result.sources
            ),
            "time_to_self_routing_seconds": (
                round(
                    self_routing_time,
                    4,
                )
                if self_routing_time
                is not None
                else None
            ),
            "time_to_first_spoken_seconds": (
                round(
                    first_spoken_time,
                    4,
                )
                if first_spoken_time
                is not None
                else None
            ),
            "context_resolution_seconds": (
                timings.get(
                    "context_resolution_seconds"
                )
            ),
            "total_response_seconds": round(
                total_time,
                4,
            ),
            "response": result.response,
            "route_header_leaked": (
                "<route>" in result.response
                or "</route>" in result.response
            ),
            "event_types": event_types,
        }
    except Exception as error:
        return {
            "success": False,
            "case_id": case["case_id"],
            "text": case["text"],
            "repetition": repetition,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": (
                type(error).__name__
            ),
            "error": str(error),
        }


def build_summary(
    results: list[dict],
) -> dict:
    valid = [
        result
        for result in results
        if result["success"]
    ]

    def count(field: str) -> int:
        return sum(
            result[field]
            for result in valid
        )

    return {
        "successful_samples": len(valid),
        "valid_route_blocks": count(
            "route_valid"
        ),
        "route_accuracy": count(
            "route_correct"
        ),
        "retrieval_available_accuracy": (
            count(
                "retrieval_available_correct"
            )
        ),
        "retrieval_used_accuracy": count(
            "retrieval_used_correct"
        ),
        "candidate_subjects_accuracy": count(
            "candidate_subjects_correct"
        ),
        "proposed_action_accuracy": count(
            "proposed_action_correct"
        ),
        "tool_accuracy": count(
            "tool_correct"
        ),
        "route_header_leaks": sum(
            result["route_header_leaked"]
            for result in valid
        ),
        "median_time_to_self_routing_seconds": (
            median(
                [
                    result[
                        "time_to_self_routing_seconds"
                    ]
                    for result in valid
                    if result[
                        "time_to_self_routing_seconds"
                    ] is not None
                ]
            )
        ),
        "median_time_to_first_spoken_seconds": (
            median(
                [
                    result[
                        "time_to_first_spoken_seconds"
                    ]
                    for result in valid
                    if result[
                        "time_to_first_spoken_seconds"
                    ] is not None
                ]
            )
        ),
        "median_total_response_seconds": (
            median(
                [
                    result[
                        "total_response_seconds"
                    ]
                    for result in valid
                ]
            )
        ),
        "median_context_resolution_seconds": (
            median(
                [
                    result[
                        "context_resolution_seconds"
                    ]
                    for result in valid
                    if result[
                        "context_resolution_seconds"
                    ] is not None
                ]
            )
        ),
    }


def write_markdown(
    path: Path,
    report: dict,
) -> None:
    summary = report["summary"]
    count = summary["successful_samples"]
    lines = [
        "# Context-resolver self-routing benchmark",
        "",
        f"Model: `{report['model']}`",
        "",
        f"Thinking: `{report['think']}`",
        "",
        "| Metric | Result |",
        "|---|---:|",
        (
            "| Valid route blocks | "
            f"{summary['valid_route_blocks']}/{count} |"
        ),
        (
            "| Route accuracy | "
            f"{summary['route_accuracy']}/{count} |"
        ),
        (
            "| Retrieval-available accuracy | "
            f"{summary['retrieval_available_accuracy']}/{count} |"
        ),
        (
            "| Retrieval-used accuracy | "
            f"{summary['retrieval_used_accuracy']}/{count} |"
        ),
        (
            "| Candidate-subject accuracy | "
            f"{summary['candidate_subjects_accuracy']}/{count} |"
        ),
        (
            "| Proposed-action accuracy | "
            f"{summary['proposed_action_accuracy']}/{count} |"
        ),
        (
            "| Tool accuracy | "
            f"{summary['tool_accuracy']}/{count} |"
        ),
        (
            "| Median self-routing time | "
            f"{summary['median_time_to_self_routing_seconds']}s |"
        ),
        (
            "| Median first spoken time | "
            f"{summary['median_time_to_first_spoken_seconds']}s |"
        ),
        (
            "| Median complete response | "
            f"{summary['median_total_response_seconds']}s |"
        ),
        (
            "| Route-header leaks | "
            f"{summary['route_header_leaks']} |"
        ),
        "",
        "## Samples",
        "",
        "| Case | Run | Valid | Route | Retrieval used | Candidate | Tool | Route time | First speech | Total |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for result in report["results"]:
        lines.append(
            f"| {result['case_id']} | "
            f"{result['repetition']} | "
            f"{result.get('route_valid')} | "
            f"{result.get('route_correct')} | "
            f"{result.get('retrieval_used_correct')} | "
            f"{result.get('candidate_subjects_correct')} | "
            f"{result.get('tool_correct')} | "
            f"{result.get('time_to_self_routing_seconds')}s | "
            f"{result.get('time_to_first_spoken_seconds')}s | "
            f"{result.get('total_response_seconds')}s |"
        )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        required=True,
    )
    parser.add_argument(
        "--think",
        choices=["false", "true"],
        required=True,
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    arguments = parser.parse_args()
    think = arguments.think == "true"
    settings.ollama_model = arguments.model
    settings.ollama_main_think = think
    results = []
    sample_total = (
        len(CASES)
        * arguments.repetitions
    )
    sample_number = 0

    for repetition in range(
        1,
        arguments.repetitions + 1,
    ):
        for case in CASES:
            sample_number += 1
            print(
                f"{sample_number:02d}/"
                f"{sample_total} "
                f"{case['case_id']} "
                f"run={repetition}",
                flush=True,
            )
            result = run_sample(
                case=case,
                repetition=repetition,
            )
            results.append(result)
            print(
                json.dumps(
                    {
                        "success": result[
                            "success"
                        ],
                        "route_valid": (
                            result.get(
                                "route_valid"
                            )
                        ),
                        "route_correct": (
                            result.get(
                                "route_correct"
                            )
                        ),
                        "retrieval_used": (
                            result.get(
                                "retrieval_used_correct"
                            )
                        ),
                        "candidate": (
                            result.get(
                                "candidate_subjects_correct"
                            )
                        ),
                        "tool": result.get(
                            "tool_correct"
                        ),
                        "first_spoken": (
                            result.get(
                                "time_to_first_spoken_seconds"
                            )
                        ),
                        "total": result.get(
                            "total_response_seconds"
                        ),
                        "error": result.get(
                            "error"
                        ),
                    },
                    indent=2,
                ),
                flush=True,
            )

    report = {
        "model": arguments.model,
        "think": think,
        "repetitions": (
            arguments.repetitions
        ),
        "case_count": len(CASES),
        "sample_count": len(results),
        "summary": build_summary(results),
        "results": results,
    }
    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    arguments.output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    markdown_path = (
        arguments.output.with_suffix(".md")
    )
    write_markdown(
        markdown_path,
        report,
    )
    print(
        json.dumps(
            report["summary"],
            indent=2,
        ),
        flush=True,
    )
    print(
        f"JSON report: {arguments.output}",
        flush=True,
    )
    print(
        f"Markdown report: {markdown_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
