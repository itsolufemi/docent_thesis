from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path
from time import perf_counter

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from config import settings  # noqa: E402
from conversation_core.schemas.trp_schemas import (  # noqa: E402
    TRPPrediction,
)
from conversation_core.services.trp_service import (  # noqa: E402
    build_trp_prompt,
    parse_trp_prediction_json,
)
from scripts.benchmark_trp_accuracy import (  # noqa: E402
    TRP_ACCURACY_CASES,
    percentile,
)
from scripts.benchmark_trp_models import (  # noqa: E402
    call_structured_trp_model,
)


MODEL_NAME = "gemma4:cloud"

TRP_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "trp_probability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "turn_complete": {
            "type": "boolean",
        },
        "reason": {
            "type": "string",
        },
    },
    "required": [
        "trp_probability",
        "turn_complete",
        "reason",
    ],
}

PROBABILITY_PATTERN = re.compile(
    r'"trp_probability"\s*:\s*'
    r'(-?(?:\d+(?:\.\d*)?|\.\d+))'
)
TURN_COMPLETE_PATTERN = re.compile(
    r'"turn_complete"\s*:\s*'
    r'(true|false)'
)


def build_payload(
    *,
    case: dict,
    stream: bool,
) -> dict:
    return {
        "model": MODEL_NAME,
        "prompt": build_trp_prompt(
            partial_utterance=(
                case["utterance"]
            ),
            previous_turns=(
                case["previous_turns"]
            ),
        ),
        "stream": stream,
        "think": False,
        "format": TRP_JSON_SCHEMA,
        "options": {
            "temperature": 0,
            "num_predict": 160,
        },
    }


def call_streaming_trp(
    case: dict,
) -> dict:
    started_at = perf_counter()
    first_content_seconds = None
    decision_fields_seconds = None
    valid_json_seconds = None
    response_complete_seconds = None
    accumulated_response = ""
    parsed_prediction = None
    streamed_probability = None
    streamed_turn_complete = None
    chunk_count = 0

    try:
        with httpx.stream(
            method="POST",
            url=(
                f"{settings.ollama_base_url}"
                "/api/generate"
            ),
            json=build_payload(
                case=case,
                stream=True,
            ),
            timeout=30.0,
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                chunk = json.loads(line)
                content = chunk.get(
                    "response",
                    "",
                )

                if content:
                    chunk_count += 1
                    accumulated_response += (
                        content
                    )

                    if (
                        first_content_seconds
                        is None
                    ):
                        first_content_seconds = (
                            perf_counter()
                            - started_at
                        )

                    if (
                        decision_fields_seconds
                        is None
                    ):
                        probability_match = (
                            PROBABILITY_PATTERN
                            .search(
                                accumulated_response
                            )
                        )
                        turn_match = (
                            TURN_COMPLETE_PATTERN
                            .search(
                                accumulated_response
                            )
                        )

                        if (
                            probability_match
                            and turn_match
                        ):
                            streamed_probability = (
                                float(
                                    probability_match
                                    .group(1)
                                )
                            )
                            streamed_turn_complete = (
                                turn_match.group(1)
                                == "true"
                            )
                            decision_fields_seconds = (
                                perf_counter()
                                - started_at
                            )

                    if (
                        valid_json_seconds
                        is None
                    ):
                        try:
                            parsed_prediction = (
                                TRPPrediction
                                .model_validate(
                                    parse_trp_prediction_json(
                                        accumulated_response
                                    )
                                )
                            )
                        except Exception:
                            pass
                        else:
                            valid_json_seconds = (
                                perf_counter()
                                - started_at
                            )

                if chunk.get("done"):
                    response_complete_seconds = (
                        perf_counter()
                        - started_at
                    )
                    break

        if parsed_prediction is None:
            raise ValueError(
                "The stream never produced valid "
                "TRP JSON."
            )

        elapsed_seconds = (
            perf_counter() - started_at
        )
        threshold_decision = (
            parsed_prediction
            .trp_probability
            >= 0.70
        )
        return {
            "success": True,
            "elapsed_seconds": round(
                elapsed_seconds,
                4,
            ),
            "first_content_seconds": round(
                first_content_seconds,
                4,
            ),
            "decision_fields_seconds": (
                round(
                    decision_fields_seconds,
                    4,
                )
            ),
            "valid_json_seconds": round(
                valid_json_seconds,
                4,
            ),
            "response_complete_seconds": (
                round(
                    (
                        response_complete_seconds
                        if (
                            response_complete_seconds
                            is not None
                        )
                        else elapsed_seconds
                    ),
                    4,
                )
            ),
            "chunk_count": chunk_count,
            "trp_probability": (
                parsed_prediction
                .trp_probability
            ),
            "model_turn_complete": (
                parsed_prediction
                .turn_complete
            ),
            "turn_complete": (
                threshold_decision
            ),
            "streamed_probability": (
                streamed_probability
            ),
            "streamed_turn_complete": (
                streamed_turn_complete
            ),
            "reason": (
                parsed_prediction.reason
            ),
        }
    except Exception as error:
        return {
            "success": False,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": (
                type(error).__name__
            ),
            "error": str(error),
        }


def decorate_result(
    *,
    mode: str,
    case: dict,
    sample: dict,
) -> dict:
    result = {
        "mode": mode,
        "case_id": case["case_id"],
        "utterance": case["utterance"],
        "expected_complete": (
            case["expected_complete"]
        ),
        **sample,
    }

    if sample["success"]:
        result["correct"] = (
            sample["turn_complete"]
            == case["expected_complete"]
        )
    else:
        result["correct"] = False

    return result


def summarise_mode(
    *,
    mode: str,
    results: list[dict],
) -> dict:
    valid_results = [
        result
        for result in results
        if result["success"]
    ]
    elapsed_values = [
        result["elapsed_seconds"]
        for result in valid_results
    ]
    summary = {
        "mode": mode,
        "total_cases": len(results),
        "valid_cases": len(valid_results),
        "correct_cases": sum(
            result["correct"]
            for result in valid_results
        ),
        "median_elapsed_seconds": round(
            statistics.median(
                elapsed_values
            ),
            4,
        ),
        "mean_elapsed_seconds": round(
            statistics.mean(
                elapsed_values
            ),
            4,
        ),
        "p95_elapsed_seconds": round(
            percentile(
                elapsed_values,
                0.95,
            ),
            4,
        ),
        "minimum_elapsed_seconds": min(
            elapsed_values
        ),
        "maximum_elapsed_seconds": max(
            elapsed_values
        ),
    }

    if mode == "streaming":
        for field_name in [
            "first_content_seconds",
            "decision_fields_seconds",
            "valid_json_seconds",
            "response_complete_seconds",
        ]:
            values = [
                result[field_name]
                for result in valid_results
            ]
            summary[
                f"median_{field_name}"
            ] = round(
                statistics.median(values),
                4,
            )
            summary[
                f"p95_{field_name}"
            ] = round(
                percentile(values, 0.95),
                4,
            )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "tmp/latency/"
            "trp_streaming_comparison.json"
        ),
    )
    arguments = parser.parse_args()
    warmup_case = TRP_ACCURACY_CASES[0]
    warmups = {
        "non_streaming": (
            call_structured_trp_model(
                model=MODEL_NAME,
                transcript=(
                    warmup_case["utterance"]
                ),
                previous_turns=(
                    warmup_case[
                        "previous_turns"
                    ]
                ),
            )
        ),
        "streaming": call_streaming_trp(
            warmup_case
        ),
    }

    print(
        "Warmups: "
        f"non-streaming="
        f"{warmups['non_streaming']['elapsed_seconds']:.4f}s, "
        f"streaming="
        f"{warmups['streaming']['elapsed_seconds']:.4f}s",
        flush=True,
    )

    work_items = [
        (mode, case)
        for case in TRP_ACCURACY_CASES
        for mode in [
            "non_streaming",
            "streaming",
        ]
    ]
    random_generator = random.Random(
        20260729
    )
    random_generator.shuffle(work_items)
    results_by_mode = {
        "non_streaming": [],
        "streaming": [],
    }

    for work_index, (
        mode,
        case,
    ) in enumerate(
        work_items,
        start=1,
    ):
        if mode == "streaming":
            sample = call_streaming_trp(
                case
            )
        else:
            sample = (
                call_structured_trp_model(
                    model=MODEL_NAME,
                    transcript=(
                        case["utterance"]
                    ),
                    previous_turns=(
                        case[
                            "previous_turns"
                        ]
                    ),
                )
            )

        result = decorate_result(
            mode=mode,
            case=case,
            sample=sample,
        )
        results_by_mode[mode].append(
            result
        )
        print(
            f"{work_index:02d}/"
            f"{len(work_items)} "
            f"{mode} "
            f"{case['case_id']}: "
            f"correct={result['correct']} "
            f"seconds="
            f"{sample['elapsed_seconds']:.4f}",
            flush=True,
        )

    summaries = {
        mode: summarise_mode(
            mode=mode,
            results=results,
        )
        for mode, results
        in results_by_mode.items()
    }
    paired_results = []
    unpaired_failures = []

    for case in TRP_ACCURACY_CASES:
        non_streaming_result = next(
            result
            for result in (
                results_by_mode[
                    "non_streaming"
                ]
            )
            if (
                result["case_id"]
                == case["case_id"]
            )
        )
        streaming_result = next(
            result
            for result in (
                results_by_mode[
                    "streaming"
                ]
            )
            if (
                result["case_id"]
                == case["case_id"]
            )
        )

        if (
            not non_streaming_result[
                "success"
            ]
            or not streaming_result[
                "success"
            ]
        ):
            unpaired_failures.append(
                {
                    "case_id": (
                        case["case_id"]
                    ),
                    "non_streaming_success": (
                        non_streaming_result[
                            "success"
                        ]
                    ),
                    "streaming_success": (
                        streaming_result[
                            "success"
                        ]
                    ),
                    "non_streaming_error": (
                        non_streaming_result
                        .get("error")
                    ),
                    "streaming_error": (
                        streaming_result
                        .get("error")
                    ),
                }
            )
            continue

        paired_results.append(
            {
                "case_id": case["case_id"],
                "non_streaming_seconds": (
                    non_streaming_result[
                        "elapsed_seconds"
                    ]
                ),
                "streaming_valid_json_seconds": (
                    streaming_result[
                        "valid_json_seconds"
                    ]
                ),
                "streaming_decision_fields_seconds": (
                    streaming_result[
                        "decision_fields_seconds"
                    ]
                ),
                "valid_json_saving_seconds": (
                    round(
                        non_streaming_result[
                            "elapsed_seconds"
                        ]
                        - streaming_result[
                            "valid_json_seconds"
                        ],
                        4,
                    )
                ),
                "decision_fields_saving_seconds": (
                    round(
                        non_streaming_result[
                            "elapsed_seconds"
                        ]
                        - streaming_result[
                            "decision_fields_seconds"
                        ],
                        4,
                    )
                ),
            }
        )

    valid_json_savings = [
        result[
            "valid_json_saving_seconds"
        ]
        for result in paired_results
    ]
    decision_field_savings = [
        result[
            "decision_fields_saving_seconds"
        ]
        for result in paired_results
    ]
    report = {
        "model": MODEL_NAME,
        "profile": (
            "structured_json_thinking_disabled"
        ),
        "case_count": len(
            TRP_ACCURACY_CASES
        ),
        "warmups": warmups,
        "summaries": summaries,
        "results_by_mode": (
            results_by_mode
        ),
        "paired_results": paired_results,
        "unpaired_failures": (
            unpaired_failures
        ),
        "paired_summary": {
            "valid_pair_count": len(
                paired_results
            ),
            "failed_pair_count": len(
                unpaired_failures
            ),
            "median_valid_json_saving_seconds": (
                round(
                    statistics.median(
                        valid_json_savings
                    ),
                    4,
                )
            ),
            "mean_valid_json_saving_seconds": (
                round(
                    statistics.mean(
                        valid_json_savings
                    ),
                    4,
                )
            ),
            "streaming_valid_json_faster_cases": (
                sum(
                    value > 0
                    for value
                    in valid_json_savings
                )
            ),
            "median_decision_fields_saving_seconds": (
                round(
                    statistics.median(
                        decision_field_savings
                    ),
                    4,
                )
            ),
            "streaming_decision_fields_faster_cases": (
                sum(
                    value > 0
                    for value
                    in decision_field_savings
                )
            ),
        },
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

    print("\nSummary:", flush=True)
    print(
        json.dumps(
            {
                "summaries": summaries,
                "paired_summary": (
                    report[
                        "paired_summary"
                    ]
                ),
            },
            indent=2,
        ),
        flush=True,
    )
    print(
        f"Full report: {arguments.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
