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
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from docent.services.docent_query_service import (  # noqa: E402
    docent_model_routing_query_engine,
)


CASES = [
    {
        "case_id": "artwork_information",
        "text": (
            "Tell me about The Arab Tent."
        ),
        "route_type": "response_request",
        "retrieval_required": True,
        "retrieved_context_used": True,
        "action_required": False,
        "expected_tool": None,
    },
    {
        "case_id": "greeting",
        "text": "Hi, how are you?",
        "route_type": "response_request",
        "retrieval_required": False,
        "retrieved_context_used": False,
        "action_required": False,
        "expected_tool": None,
    },
    {
        "case_id": "highlights_tour",
        "text": (
            "Start a highlights tour."
        ),
        "route_type": "call_to_action",
        "retrieval_required": True,
        "retrieved_context_used": True,
        "action_required": True,
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
        "retrieval_required": False,
        "retrieved_context_used": False,
        "action_required": False,
        "expected_tool": None,
    },
]


def rounded_median(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return round(
        statistics.median(values),
        4,
    )


def route_agrees(
    *,
    route: dict | None,
    case: dict,
) -> bool:
    if route is None:
        return False

    route_type_agrees = (
        route["route_type"]
        == case["route_type"]
    )

    if case["case_id"] == "noise":
        route_type_agrees = (
            route["route_type"] == "noise"
            or route["should_ignore"] is True
        )

    action_agrees = (
        bool(route.get("proposed_action"))
        == case["action_required"]
    )

    return (
        route_type_agrees
        and route["retrieval_required"]
        == case["retrieval_required"]
        and route["retrieved_context_used"]
        == case["retrieved_context_used"]
        and action_agrees
    )


def tool_call_is_correct(
    *,
    tool_calls: list[str],
    tool_results: list[dict],
    case: dict,
) -> bool:
    expected_tool = case["expected_tool"]

    if expected_tool is None:
        return not tool_calls

    matching_results = [
        result
        for result in tool_results
        if (
            result.get("tool_name")
            == expected_tool
        )
    ]

    return (
        expected_tool in tool_calls
        and bool(matching_results)
        and all(
            result.get("success") is True
            for result in matching_results
        )
    )


def run_sample(
    *,
    case: dict,
    repetition: int,
) -> dict:
    started_at = perf_counter()
    route_event_seconds = None
    first_spoken_seconds = None
    route = None
    tool_calls: list[str] = []
    tool_results: list[dict] = []
    event_types: list[str] = []

    def on_stream_event(
        event: LLMStreamEvent,
    ) -> None:
        nonlocal route_event_seconds
        nonlocal first_spoken_seconds
        nonlocal route

        event_types.append(event.event_type)
        elapsed = perf_counter() - started_at

        if (
            event.event_type
            == "route_assessment"
        ):
            route_event_seconds = elapsed
            route = event.route_assessment

        if (
            event.event_type
            == "content_delta"
            and event.text
            and first_spoken_seconds is None
        ):
            first_spoken_seconds = elapsed

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
            docent_model_routing_query_engine
            .generate_streaming_response(
                text=case["text"],
                include_debug=True,
                on_stream_event=on_stream_event,
            )
        )
        total_seconds = (
            perf_counter() - started_at
        )
        debug_payload = (
            result.debug.debug_payload
            if result.debug is not None
            else {}
        )
        route = (
            route
            or debug_payload.get(
                "model_route_assessment"
            )
        )
        model_route_valid = bool(
            debug_payload.get(
                "model_route_valid"
            )
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
            "route": route,
            "model_route_valid": (
                model_route_valid
            ),
            "route_agreement": route_agrees(
                route=route,
                case=case,
            ),
            "tool_call_correct": (
                tool_call_is_correct(
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    case=case,
                )
            ),
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "time_to_route_event_seconds": (
                round(
                    route_event_seconds,
                    4,
                )
                if route_event_seconds
                is not None
                else None
            ),
            "time_to_first_spoken_token_seconds": (
                round(
                    first_spoken_seconds,
                    4,
                )
                if first_spoken_seconds
                is not None
                else None
            ),
            "context_resolution_seconds": (
                timings.get(
                    "context_resolution_seconds"
                )
            ),
            "model_route_block_seconds": (
                timings.get(
                    "model_route_block_seconds"
                )
            ),
            "response_generation_seconds": (
                timings.get(
                    "response_generation_seconds"
                )
            ),
            "total_response_seconds": round(
                total_seconds,
                4,
            ),
            "response": result.response,
            "route_header_leaked": (
                "<route>" in result.response
                or "</route>" in result.response
            ),
            "event_types": event_types,
            "sources_count": len(
                result.sources
            ),
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
    route_valid = [
        result
        for result in valid
        if result["model_route_valid"]
    ]
    route_times = [
        result[
            "time_to_route_event_seconds"
        ]
        for result in valid
        if result[
            "time_to_route_event_seconds"
        ] is not None
    ]
    first_spoken_times = [
        result[
            "time_to_first_spoken_token_seconds"
        ]
        for result in valid
        if result[
            "time_to_first_spoken_token_seconds"
        ] is not None
    ]

    return {
        "successful_samples": len(valid),
        "route_valid_samples": len(route_valid),
        "route_validity_rate": round(
            len(route_valid) / len(valid),
            4,
        )
        if valid
        else 0.0,
        "route_agreement_samples": sum(
            result["route_agreement"]
            for result in valid
        ),
        "route_agreement_rate": round(
            sum(
                result["route_agreement"]
                for result in valid
            )
            / len(valid),
            4,
        )
        if valid
        else 0.0,
        "tool_correct_samples": sum(
            result["tool_call_correct"]
            for result in valid
        ),
        "tool_correct_rate": round(
            sum(
                result["tool_call_correct"]
                for result in valid
            )
            / len(valid),
            4,
        )
        if valid
        else 0.0,
        "route_header_leaks": sum(
            result["route_header_leaked"]
            for result in valid
        ),
        "median_time_to_route_event_seconds": (
            rounded_median(route_times)
        ),
        "median_time_to_first_spoken_token_seconds": (
            rounded_median(
                first_spoken_times
            )
        ),
        "median_total_response_seconds": (
            rounded_median(
                [
                    result[
                        "total_response_seconds"
                    ]
                    for result in valid
                ]
            )
        ),
        "median_context_resolution_seconds": (
            rounded_median(
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
    lines = [
        "# Model self-routing benchmark",
        "",
        f"Model: `{report['model']}`",
        "",
        (
            "Thinking: "
            f"`{report['think']}`"
        ),
        "",
        (
            "Architecture: retrieval prefetch followed "
            "by one main-model conversation that emits "
            "a hidden route header and the spoken answer."
        ),
        "",
        "| Metric | Result |",
        "|---|---:|",
        (
            "| Valid route blocks | "
            f"{summary['route_valid_samples']}/"
            f"{summary['successful_samples']} |"
        ),
        (
            "| Label agreement | "
            f"{summary['route_agreement_samples']}/"
            f"{summary['successful_samples']} |"
        ),
        (
            "| Tool correctness | "
            f"{summary['tool_correct_samples']}/"
            f"{summary['successful_samples']} |"
        ),
        (
            "| Median time to route block | "
            f"{summary['median_time_to_route_event_seconds']}s |"
        ),
        (
            "| Median time to first spoken token | "
            f"{summary['median_time_to_first_spoken_token_seconds']}s |"
        ),
        (
            "| Median full response time | "
            f"{summary['median_total_response_seconds']}s |"
        ),
        (
            "| Route-header leaks | "
            f"{summary['route_header_leaks']} |"
        ),
        "",
        "## Samples",
        "",
        "| Case | Run | Valid | Agrees | Tool correct | Route | First spoken | Total |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for result in report["results"]:
        route = result.get("route") or {}
        lines.append(
            f"| {result['case_id']} | "
            f"{result['repetition']} | "
            f"{result.get('model_route_valid')} | "
            f"{result.get('route_agreement')} | "
            f"{result.get('tool_call_correct')} | "
            f"{route.get('route_type', 'n/a')} | "
            f"{result.get('time_to_first_spoken_token_seconds')}s | "
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
    total = (
        len(CASES)
        * arguments.repetitions
    )
    sample_index = 0

    for repetition in range(
        1,
        arguments.repetitions + 1,
    ):
        for case in CASES:
            sample_index += 1
            print(
                f"{sample_index:02d}/{total} "
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
                                "model_route_valid"
                            )
                        ),
                        "route_agreement": (
                            result.get(
                                "route_agreement"
                            )
                        ),
                        "tool_correct": (
                            result.get(
                                "tool_call_correct"
                            )
                        ),
                        "first_spoken": (
                            result.get(
                                "time_to_first_spoken_token_seconds"
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
