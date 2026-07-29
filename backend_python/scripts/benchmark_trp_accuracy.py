from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from scripts.benchmark_trp_models import (  # noqa: E402
    call_structured_trp_model,
)


DEFAULT_MODELS = [
    "gemma4:cloud",
    "gpt-oss:20b-cloud",
]


TRP_ACCURACY_CASES = [
    {
        "case_id": "complete_01",
        "utterance": (
            "Tell me about The Arab Tent."
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_request",
    },
    {
        "case_id": "complete_02",
        "utterance": (
            "Who painted The Swing?"
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_question",
    },
    {
        "case_id": "complete_03",
        "utterance": (
            "I think that the painting "
            "is beautiful."
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_statement",
    },
    {
        "case_id": "complete_04",
        "utterance": "Yes, please.",
        "expected_complete": True,
        "previous_turns": [
            (
                "assistant: Would you like "
                "to hear more about it?"
            ),
        ],
        "category": "contextual_answer",
    },
    {
        "case_id": "complete_05",
        "utterance": "Its history.",
        "expected_complete": True,
        "previous_turns": [
            (
                "assistant: Would you like "
                "to hear about its history "
                "or its composition?"
            ),
        ],
        "category": "contextual_answer",
    },
    {
        "case_id": "complete_06",
        "utterance": "No, thank you.",
        "expected_complete": True,
        "previous_turns": [
            (
                "assistant: Shall I continue "
                "the tour?"
            ),
        ],
        "category": "contextual_answer",
    },
    {
        "case_id": "complete_07",
        "utterance": (
            "Start a highlights tour."
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_command",
    },
    {
        "case_id": "complete_08",
        "utterance": (
            "When was The Swing painted?"
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_question",
    },
    {
        "case_id": "complete_09",
        "utterance": (
            "The colours make it feel joyful."
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_statement",
    },
    {
        "case_id": "complete_10",
        "utterance": (
            "Let's move to the next room."
        ),
        "expected_complete": True,
        "previous_turns": [],
        "category": "complete_command",
    },
    {
        "case_id": "incomplete_01",
        "utterance": "Tell me about",
        "expected_complete": False,
        "previous_turns": [],
        "category": "trailing_preposition",
    },
    {
        "case_id": "incomplete_02",
        "utterance": "I think that",
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_clause",
    },
    {
        "case_id": "incomplete_03",
        "utterance": (
            "I think that the painting is"
        ),
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_predicate",
    },
    {
        "case_id": "incomplete_04",
        "utterance": "Who painted",
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_question",
    },
    {
        "case_id": "incomplete_05",
        "utterance": "When was",
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_question",
    },
    {
        "case_id": "incomplete_06",
        "utterance": (
            "The artist seems to have"
        ),
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_predicate",
    },
    {
        "case_id": "incomplete_07",
        "utterance": (
            "If we move to the next room"
        ),
        "expected_complete": False,
        "previous_turns": [],
        "category": "subordinate_clause",
    },
    {
        "case_id": "incomplete_08",
        "utterance": (
            "What I find most interesting is"
        ),
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_predicate",
    },
    {
        "case_id": "incomplete_09",
        "utterance": (
            "Can you tell me whether"
        ),
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_clause",
    },
    {
        "case_id": "incomplete_10",
        "utterance": (
            "Compared with The Swing, "
            "this painting"
        ),
        "expected_complete": False,
        "previous_turns": [],
        "category": "unfinished_comparison",
    },
]


def percentile(
    values: list[float],
    percentile_value: float,
) -> float | None:
    if not values:
        return None

    ordered_values = sorted(values)
    position = (
        (len(ordered_values) - 1)
        * percentile_value
    )
    lower_index = int(position)
    upper_index = min(
        lower_index + 1,
        len(ordered_values) - 1,
    )
    fraction = position - lower_index
    return (
        ordered_values[lower_index]
        + (
            ordered_values[upper_index]
            - ordered_values[lower_index]
        )
        * fraction
    )


def summarise_model(
    model: str,
    results: list[dict],
) -> dict:
    valid_results = [
        result
        for result in results
        if result["success"]
    ]
    complete_cases = [
        result
        for result in valid_results
        if result["expected_complete"]
    ]
    incomplete_cases = [
        result
        for result in valid_results
        if not result["expected_complete"]
    ]
    true_positives = sum(
        result["predicted_complete"]
        for result in complete_cases
    )
    false_negatives = (
        len(complete_cases)
        - true_positives
    )
    false_positives = sum(
        result["predicted_complete"]
        for result in incomplete_cases
    )
    true_negatives = (
        len(incomplete_cases)
        - false_positives
    )
    correct_count = (
        true_positives + true_negatives
    )
    model_boolean_correct_count = sum(
        result["model_boolean_correct"]
        for result in valid_results
    )
    valid_count = len(valid_results)
    timings = [
        result["elapsed_seconds"]
        for result in valid_results
    ]
    complete_recall = (
        true_positives
        / len(complete_cases)
        if complete_cases
        else 0.0
    )
    incomplete_recall = (
        true_negatives
        / len(incomplete_cases)
        if incomplete_cases
        else 0.0
    )

    return {
        "model": model,
        "total_cases": len(results),
        "valid_cases": valid_count,
        "correct_cases": correct_count,
        "accuracy": round(
            (
                correct_count / valid_count
                if valid_count
                else 0.0
            ),
            4,
        ),
        "balanced_accuracy": round(
            (
                complete_recall
                + incomplete_recall
            )
            / 2,
            4,
        ),
        "model_boolean_correct_cases": (
            model_boolean_correct_count
        ),
        "model_boolean_accuracy": round(
            (
                model_boolean_correct_count
                / valid_count
                if valid_count
                else 0.0
            ),
            4,
        ),
        "true_positives": true_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "false_positives": false_positives,
        "complete_recall": round(
            complete_recall,
            4,
        ),
        "incomplete_recall": round(
            incomplete_recall,
            4,
        ),
        "median_latency_seconds": (
            round(
                statistics.median(timings),
                4,
            )
            if timings
            else None
        ),
        "mean_latency_seconds": (
            round(
                statistics.mean(timings),
                4,
            )
            if timings
            else None
        ),
        "p95_latency_seconds": (
            round(
                percentile(
                    timings,
                    0.95,
                ),
                4,
            )
            if timings
            else None
        ),
        "minimum_latency_seconds": (
            min(timings)
            if timings
            else None
        ),
        "maximum_latency_seconds": (
            max(timings)
            if timings
            else None
        ),
        "incorrect_cases": [
            result
            for result in valid_results
            if not result["correct"]
        ],
        "failed_cases": [
            result
            for result in results
            if not result["success"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "tmp/latency/"
            "trp_balanced_accuracy.json"
        ),
    )
    arguments = parser.parse_args()
    random_generator = random.Random(
        20260729
    )

    print(
        "Warming each model...",
        flush=True,
    )
    warmups = {}

    for model in arguments.models:
        warmups[model] = (
            call_structured_trp_model(
                model=model,
                transcript=(
                    "Tell me about "
                    "The Arab Tent."
                ),
                previous_turns=[],
            )
        )
        print(
            f"{model}: "
            f"{warmups[model]['elapsed_seconds']:.4f}s "
            f"success="
            f"{warmups[model]['success']}",
            flush=True,
        )

    work_items = [
        (model, case)
        for case in TRP_ACCURACY_CASES
        for model in arguments.models
    ]
    random_generator.shuffle(work_items)
    results_by_model = {
        model: []
        for model in arguments.models
    }

    for work_index, (
        model,
        case,
    ) in enumerate(
        work_items,
        start=1,
    ):
        sample = call_structured_trp_model(
            model=model,
            transcript=case["utterance"],
            previous_turns=(
                case["previous_turns"]
            ),
        )
        result = {
            "case_id": case["case_id"],
            "category": case["category"],
            "utterance": case["utterance"],
            "previous_turns": (
                case["previous_turns"]
            ),
            "expected_complete": (
                case["expected_complete"]
            ),
            **sample,
        }

        if sample["success"]:
            result["predicted_complete"] = (
                sample["turn_complete"]
            )
            result["correct"] = (
                sample["turn_complete"]
                == case["expected_complete"]
            )
            result[
                "model_boolean_correct"
            ] = (
                sample[
                    "model_turn_complete"
                ]
                == case["expected_complete"]
            )
        else:
            result["predicted_complete"] = (
                None
            )
            result["correct"] = False
            result[
                "model_boolean_correct"
            ] = False

        results_by_model[model].append(
            result
        )
        print(
            f"{work_index:02d}/"
            f"{len(work_items)} "
            f"{model} "
            f"{case['case_id']}: "
            f"expected="
            f"{case['expected_complete']} "
            f"predicted="
            f"{result['predicted_complete']} "
            f"correct={result['correct']} "
            f"seconds="
            f"{sample['elapsed_seconds']:.4f}",
            flush=True,
        )

    summaries = [
        summarise_model(
            model,
            results_by_model[model],
        )
        for model in arguments.models
    ]
    ranking = sorted(
        summaries,
        key=lambda summary: (
            -summary["balanced_accuracy"],
            (
                summary[
                    "median_latency_seconds"
                ]
                if (
                    summary[
                        "median_latency_seconds"
                    ]
                    is not None
                )
                else float("inf")
            ),
        ),
    )
    report = {
        "profile": (
            "structured_json_low_reasoning"
        ),
        "case_count": len(
            TRP_ACCURACY_CASES
        ),
        "complete_case_count": sum(
            case["expected_complete"]
            for case in TRP_ACCURACY_CASES
        ),
        "incomplete_case_count": sum(
            not case["expected_complete"]
            for case in TRP_ACCURACY_CASES
        ),
        "warmups": warmups,
        "cases": TRP_ACCURACY_CASES,
        "models": summaries,
        "results_by_model": (
            results_by_model
        ),
        "ranking": [
            summary["model"]
            for summary in ranking
        ],
    }
    arguments.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    arguments.output.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nResults:", flush=True)

    for rank, summary in enumerate(
        ranking,
        start=1,
    ):
        print(
            f"{rank}. {summary['model']}: "
            f"accuracy="
            f"{summary['accuracy']:.2%}, "
            f"balanced="
            f"{summary['balanced_accuracy']:.2%}, "
            f"false_finalisations="
            f"{summary['false_positives']}, "
            f"false_waits="
            f"{summary['false_negatives']}, "
            f"median="
            f"{summary['median_latency_seconds']}s",
            flush=True,
        )

    print(
        f"Full report: {arguments.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
