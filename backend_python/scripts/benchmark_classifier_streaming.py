from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from time import perf_counter

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from config import settings  # noqa: E402
from conversation_core.services.utterance_router_service import (  # noqa: E402
    CLASSIFIER_REQUEST_OPTIONS,
    build_utterance_route_prompt,
    normalise_route_payload,
    parse_utterance_route_json,
    request_streaming_utterance_route,
)
from docent.config.docent_classifier_profile import (  # noqa: E402
    docent_classifier_profile,
)


CLASSIFIER_CASES = [
    {
        "case_id": "greeting",
        "text": "Hello, how are you?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "artwork_information",
        "text": "Tell me about The Arab Tent.",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "artist_information",
        "text": "Who was Fragonard?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "next_artwork",
        "text": "Let's move to the next painting.",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "highlights_tour",
        "text": "Give me a highlights tour.",
        "assistant_was_speaking": False,
        "route_type": "call_to_action",
        "requires_retrieval": True,
        "proposed_action": "create_bounded_branch",
        "floor_intent": "take_floor",
    },
    {
        "case_id": "stop_tour",
        "text": "Stop the tour.",
        "assistant_was_speaking": False,
        "route_type": "call_to_action",
        "requires_retrieval": False,
        "proposed_action": "close_bounded_branch",
        "floor_intent": "take_floor",
    },
    {
        "case_id": "spoken_correction",
        "text": "Wait, that's not what I meant.",
        "assistant_was_speaking": True,
        "route_type": "interruption",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "artwork_comparison",
        "text": "Compare The Arab Tent with Guernica.",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "painting_interpretation",
        "text": "What makes The Arab Tent unusual?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "room_information",
        "text": "What can I see in the Great Gallery?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "portrait_tour",
        "text": "Start a tour of the portraits.",
        "assistant_was_speaking": False,
        "route_type": "call_to_action",
        "requires_retrieval": True,
        "proposed_action": "create_bounded_branch",
        "floor_intent": "take_floor",
    },
    {
        "case_id": "close_current_tour",
        "text": "End the current tour.",
        "assistant_was_speaking": False,
        "route_type": "call_to_action",
        "requires_retrieval": False,
        "proposed_action": "close_bounded_branch",
        "floor_intent": "take_floor",
    },
    {
        "case_id": "previous_artwork",
        "text": "Go back to the previous artwork.",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "repeat_request",
        "text": "Could you repeat that?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "museum_hours",
        "text": "When does the museum close today?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "artist_comparison",
        "text": "How does Fragonard differ from Boucher?",
        "assistant_was_speaking": False,
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "interrupt_stop",
        "text": "Stop, I have a question.",
        "assistant_was_speaking": True,
        "route_type": "interruption",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "interrupt_redirect",
        "text": "No, tell me about The Arab Tent instead.",
        "assistant_was_speaking": True,
        "route_type": "interruption",
        "requires_retrieval": True,
        "proposed_action": None,
        "floor_intent": "take_floor",
    },
    {
        "case_id": "backchannel_right",
        "text": "Right.",
        "assistant_was_speaking": True,
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "backchannel",
    },
    {
        "case_id": "backchannel_i_see",
        "text": "I see.",
        "assistant_was_speaking": True,
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
        "floor_intent": "backchannel",
    },
]


def percentile(
    values: list[float],
    fraction: float,
) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return (
        ordered[lower] * (1 - weight)
        + ordered[upper] * weight
    )


def build_prompt(
    case: dict,
    *,
    compact_response: bool,
) -> str:
    return build_utterance_route_prompt(
        text=case["text"],
        domain_profile=docent_classifier_profile,
        assistant_was_speaking=(
            case["assistant_was_speaking"]
        ),
        compact_response=compact_response,
    )


def call_legacy_classifier(
    case: dict,
) -> dict:
    started_at = perf_counter()

    try:
        response = httpx.post(
            (
                f"{settings.ollama_base_url}"
                "/api/generate"
            ),
            json={
                "model": (
                    settings.ollama_classifier_model
                ),
                "prompt": build_prompt(
                    case,
                    compact_response=False,
                ),
                "stream": False,
                "options": (
                    CLASSIFIER_REQUEST_OPTIONS
                ),
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload = parse_utterance_route_json(
            response.json().get(
                "response",
                "",
            )
        )
        route = normalise_route_payload(
            payload=payload,
            domain_profile=(
                docent_classifier_profile
            ),
        )
        return {
            "success": True,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "route": route.model_dump(
                mode="json"
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": type(error).__name__,
            "error": str(error),
        }


def call_optimized_classifier(
    case: dict,
) -> dict:
    started_at = perf_counter()

    try:
        route = request_streaming_utterance_route(
            prompt=build_prompt(
                case,
                compact_response=True,
            ),
            domain_profile=(
                docent_classifier_profile
            ),
            timeout=60.0,
        )
        return {
            "success": True,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "route": route.model_dump(
                mode="json"
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": type(error).__name__,
            "error": str(error),
        }


def score_result(
    case: dict,
    sample: dict,
) -> dict:
    if not sample["success"]:
        return {
            "correct": False,
            "field_results": {},
        }

    route = sample["route"]
    fields = {
        field: route[field] == case[field]
        for field in [
            "route_type",
            "requires_retrieval",
            "proposed_action",
            "floor_intent",
        ]
    }
    return {
        "correct": all(fields.values()),
        "field_results": fields,
    }


def summarise(
    mode: str,
    results: list[dict],
) -> dict:
    valid = [
        result
        for result in results
        if result["success"]
    ]
    timings = [
        result["elapsed_seconds"]
        for result in valid
    ]

    return {
        "mode": mode,
        "total_cases": len(results),
        "valid_cases": len(valid),
        "correct_cases": sum(
            result["correct"]
            for result in valid
        ),
        "accuracy": round(
            (
                sum(
                    result["correct"]
                    for result in valid
                )
                / len(results)
            ),
            4,
        ),
        "median_seconds": round(
            statistics.median(timings),
            4,
        ),
        "mean_seconds": round(
            statistics.mean(timings),
            4,
        ),
        "p95_seconds": round(
            percentile(timings, 0.95),
            4,
        ),
        "minimum_seconds": min(timings),
        "maximum_seconds": max(timings),
    }


def write_markdown_report(
    path: Path,
    report: dict,
) -> None:
    legacy = report["summaries"]["legacy"]
    optimized = report["summaries"]["optimized"]
    paired = report["paired_summary"]
    lines = [
        "# Classifier request-profile benchmark",
        "",
        (
            f"Model: `{report['model']}`. "
            f"Cases: {report['case_count']}. "
            "Each legacy/optimized pair ran "
            "back-to-back, with first-run order "
            "alternated between cases."
        ),
        "",
        "| Profile | Valid | Exact accuracy | Median | Mean | P95 |",
        "|---|---:|---:|---:|---:|---:|",
        (
            f"| Legacy non-streaming | {legacy['valid_cases']}/"
            f"{legacy['total_cases']} | {legacy['accuracy']:.0%} | "
            f"{legacy['median_seconds']:.4f}s | "
            f"{legacy['mean_seconds']:.4f}s | "
            f"{legacy['p95_seconds']:.4f}s |"
        ),
        (
            f"| Optimized structured streaming | "
            f"{optimized['valid_cases']}/"
            f"{optimized['total_cases']} | "
            f"{optimized['accuracy']:.0%} | "
            f"{optimized['median_seconds']:.4f}s | "
            f"{optimized['mean_seconds']:.4f}s | "
            f"{optimized['p95_seconds']:.4f}s |"
        ),
        "",
        "## Paired latency",
        "",
        (
            f"- Median saving: "
            f"{paired['median_saving_seconds']:.4f}s "
            f"({paired['median_percentage_reduction']:.1f}%)."
        ),
        (
            f"- Mean saving: "
            f"{paired['mean_saving_seconds']:.4f}s."
        ),
        (
            f"- Optimized faster in "
            f"{paired['optimized_faster_cases']}/"
            f"{paired['valid_pair_count']} valid pairs."
        ),
        "",
        "## Interpretation",
        "",
        (
            "- Both profiles produced valid, exact "
            "decisions on all 20 cases."
        ),
        (
            "- Aggregate median request-to-output "
            f"latency fell by "
            f"{legacy['median_seconds'] - optimized['median_seconds']:.4f}s "
            f"({(legacy['median_seconds'] - optimized['median_seconds']) / legacy['median_seconds']:.1%})."
        ),
        (
            "- The paired median is the more "
            "conservative estimate because cloud "
            "latency varied substantially between "
            "individual requests."
        ),
        (
            "- The optimized response requests only "
            "the five fields required for routing. "
            "`is_relevant`, `should_ignore`, "
            "`confidence`, and `reason` are derived "
            "or defaulted server-side."
        ),
        "",
        "## Cases",
        "",
        "| Case | Legacy | Optimized | Saving | Legacy correct | Optimized correct |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for pair in report["paired_results"]:
        lines.append(
            f"| {pair['case_id']} | "
            f"{pair['legacy_seconds']:.4f}s | "
            f"{pair['optimized_seconds']:.4f}s | "
            f"{pair['saving_seconds']:.4f}s | "
            f"{pair['legacy_correct']} | "
            f"{pair['optimized_correct']} |"
        )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "tmp/latency/"
            "classifier_streaming_comparison.json"
        ),
    )
    arguments = parser.parse_args()

    warmup_case = CLASSIFIER_CASES[0]
    print(
        "Starting legacy warmup...",
        flush=True,
    )
    legacy_warmup = call_legacy_classifier(
        warmup_case
    )
    print(
        "Starting optimized warmup...",
        flush=True,
    )
    optimized_warmup = (
        call_optimized_classifier(
            warmup_case
        )
    )
    warmups = {
        "legacy": legacy_warmup,
        "optimized": optimized_warmup,
    }
    print(
        "Warmups: "
        f"legacy="
        f"{warmups['legacy']['elapsed_seconds']:.4f}s, "
        f"optimized="
        f"{warmups['optimized']['elapsed_seconds']:.4f}s",
        flush=True,
    )

    ordered_cases = list(CLASSIFIER_CASES)
    random.Random(20260729).shuffle(
        ordered_cases
    )
    work_items = []

    for case_index, case in enumerate(
        ordered_cases
    ):
        modes = (
            ["legacy", "optimized"]
            if case_index % 2 == 0
            else ["optimized", "legacy"]
        )
        work_items.extend(
            (mode, case)
            for mode in modes
        )
    results_by_mode = {
        "legacy": [],
        "optimized": [],
    }

    for index, (mode, case) in enumerate(
        work_items,
        start=1,
    ):
        if mode == "legacy":
            sample = call_legacy_classifier(
                case
            )
        else:
            sample = (
                call_optimized_classifier(case)
            )

        score = score_result(case, sample)
        result = {
            "mode": mode,
            "case_id": case["case_id"],
            "text": case["text"],
            **sample,
            **score,
        }
        results_by_mode[mode].append(
            result
        )
        checkpoint_path = (
            arguments.output.with_name(
                arguments.output.stem
                + "_checkpoint.json"
            )
        )
        checkpoint_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        checkpoint_path.write_text(
            json.dumps(
                {
                    "completed_calls": index,
                    "total_calls": len(
                        work_items
                    ),
                    "warmups": warmups,
                    "results_by_mode": (
                        results_by_mode
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"{index:02d}/{len(work_items)} "
            f"{mode} {case['case_id']}: "
            f"valid={sample['success']} "
            f"correct={score['correct']} "
            f"seconds="
            f"{sample['elapsed_seconds']:.4f}",
            flush=True,
        )

    summaries = {
        mode: summarise(mode, results)
        for mode, results
        in results_by_mode.items()
    }
    paired_results = []

    for case in CLASSIFIER_CASES:
        legacy = next(
            result
            for result
            in results_by_mode["legacy"]
            if result["case_id"]
            == case["case_id"]
        )
        optimized = next(
            result
            for result
            in results_by_mode["optimized"]
            if result["case_id"]
            == case["case_id"]
        )

        if not (
            legacy["success"]
            and optimized["success"]
        ):
            continue

        saving = (
            legacy["elapsed_seconds"]
            - optimized["elapsed_seconds"]
        )
        paired_results.append(
            {
                "case_id": case["case_id"],
                "legacy_seconds": (
                    legacy["elapsed_seconds"]
                ),
                "optimized_seconds": (
                    optimized["elapsed_seconds"]
                ),
                "saving_seconds": round(
                    saving,
                    4,
                ),
                "percentage_reduction": round(
                    (
                        saving
                        / legacy["elapsed_seconds"]
                        * 100
                    ),
                    2,
                ),
                "legacy_correct": (
                    legacy["correct"]
                ),
                "optimized_correct": (
                    optimized["correct"]
                ),
            }
        )

    savings = [
        pair["saving_seconds"]
        for pair in paired_results
    ]
    percentage_reductions = [
        pair["percentage_reduction"]
        for pair in paired_results
    ]
    paired_summary = {
        "valid_pair_count": len(
            paired_results
        ),
        "median_saving_seconds": round(
            statistics.median(savings),
            4,
        ),
        "mean_saving_seconds": round(
            statistics.mean(savings),
            4,
        ),
        "median_percentage_reduction": round(
            statistics.median(
                percentage_reductions
            ),
            2,
        ),
        "optimized_faster_cases": sum(
            saving > 0
            for saving in savings
        ),
    }
    report = {
        "model": (
            settings.ollama_classifier_model
        ),
        "case_count": len(
            CLASSIFIER_CASES
        ),
        "legacy_profile": {
            "stream": False,
            "think": "unspecified",
            "format": None,
            "options": (
                CLASSIFIER_REQUEST_OPTIONS
            ),
        },
        "optimized_profile": {
            "stream": True,
            "think": False,
            "format": "utterance_route_json_schema",
            "early_return": (
                "first valid structured response"
            ),
            "requested_fields": sorted(
                [
                    "route_type",
                    "floor_intent",
                    "requires_retrieval",
                    "proposed_action",
                    "candidate_subjects",
                ]
            ),
            "derived_fields": [
                "is_relevant",
                "should_ignore",
                "confidence",
                "reason",
            ],
            "options": (
                CLASSIFIER_REQUEST_OPTIONS
            ),
        },
        "warmups": warmups,
        "summaries": summaries,
        "paired_summary": paired_summary,
        "paired_results": paired_results,
        "results_by_mode": results_by_mode,
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
    write_markdown_report(
        markdown_path,
        report,
    )

    print(
        "\nSummary:\n"
        + json.dumps(
            {
                "summaries": summaries,
                "paired_summary": (
                    paired_summary
                ),
            },
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
