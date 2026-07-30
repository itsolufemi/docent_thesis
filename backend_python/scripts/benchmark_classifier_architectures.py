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


from conversation_core.memory.conversation_store import (  # noqa: E402
    create_conversation,
    get_active_branch,
    get_recent_conversation_history,
)
from conversation_core.services.classifier_tool_orchestration_service import (  # noqa: E402
    build_classifier_tool_resume_messages,
    run_required_classifier_tool_round,
)
from conversation_core.services.llm_service import (  # noqa: E402
    stream_tool_aware_llm_messages,
    stream_tool_aware_llm_response,
)
from docent.services.docent_query_service import (  # noqa: E402
    docent_build_prompt_from_context,
    docent_resolve_context,
)
from docent.services.docent_utterance_classifier import (  # noqa: E402
    classify_docent_utterance,
)


BENCHMARK_CASES = [
    {
        "case_id": "artwork_information",
        "text": (
            "Tell me about The Arab Tent."
        ),
        "route_type": "response_request",
        "requires_retrieval": True,
        "proposed_action": None,
    },
    {
        "case_id": "greeting",
        "text": "Hi, how are you?",
        "route_type": "response_request",
        "requires_retrieval": False,
        "proposed_action": None,
    },
    {
        "case_id": "highlights_tour",
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
REPETITIONS = 3


def consume_to_first_content(
    event_stream,
) -> tuple[float, str]:
    started_at = perf_counter()

    try:
        for event in event_stream:
            if (
                event.event_type
                == "content_delta"
                and event.text
            ):
                return (
                    perf_counter() - started_at,
                    event.text,
                )
    finally:
        event_stream.close()

    raise RuntimeError(
        "The main model stream completed "
        "without a response token."
    )


def prepare_conversation_context(
    conversation_id: str,
):
    dialogue_history = (
        get_recent_conversation_history(
            conversation_id=conversation_id,
        )
    )
    active_branch = get_active_branch(
        conversation_id=conversation_id,
    )
    return dialogue_history, active_branch


def run_sequential_architecture(
    text: str,
    *,
    main_model: str,
    main_model_think: bool | None,
) -> dict:
    conversation = create_conversation()
    conversation_id = (
        conversation.conversation_id
    )
    dialogue_history, active_branch = (
        prepare_conversation_context(
            conversation_id
        )
    )
    total_started_at = perf_counter()

    classifier_started_at = perf_counter()
    route = classify_docent_utterance(
        text,
        False,
    )
    classifier_seconds = (
        perf_counter() - classifier_started_at
    )

    context_started_at = perf_counter()
    resolved_context = docent_resolve_context(
        None,
        text,
        route,
    )
    context_resolution_seconds = (
        perf_counter() - context_started_at
    )

    prompt_started_at = perf_counter()
    prompt = docent_build_prompt_from_context(
        text,
        dialogue_history,
        resolved_context,
        active_branch,
    )
    prompt_build_seconds = (
        perf_counter() - prompt_started_at
    )

    event_stream = (
        stream_tool_aware_llm_response(
            prompt=prompt,
            conversation_id=conversation_id,
            buffer_for_tool_decision=(
                route.route_type
                == "call_to_action"
            ),
            model=main_model,
            think=main_model_think,
        )
    )
    (
        model_to_first_token_seconds,
        first_token,
    ) = consume_to_first_content(
        event_stream
    )

    return {
        "success": True,
        "route": route.model_dump(
            mode="json"
        ),
        "classifier_seconds": round(
            classifier_seconds,
            4,
        ),
        "model_to_classifier_tool_seconds": (
            None
        ),
        "context_resolution_seconds": round(
            context_resolution_seconds,
            4,
        ),
        "prompt_build_seconds": round(
            prompt_build_seconds,
            4,
        ),
        "model_resume_to_first_token_seconds": (
            round(
                model_to_first_token_seconds,
                4,
            )
        ),
        "total_to_first_token_seconds": round(
            perf_counter()
            - total_started_at,
            4,
        ),
        "classifier_called_exactly_once": (
            None
        ),
        "first_token": first_token,
        "context_source": (
            resolved_context.context_source
        ),
    }


def run_classifier_tool_architecture(
    text: str,
    *,
    main_model: str,
    main_model_think: bool | None,
) -> dict:
    conversation = create_conversation()
    conversation_id = (
        conversation.conversation_id
    )
    dialogue_history, active_branch = (
        prepare_conversation_context(
            conversation_id
        )
    )
    total_started_at = perf_counter()

    classifier_round = (
        run_required_classifier_tool_round(
            text=text,
            conversation_id=conversation_id,
            main_model=main_model,
            main_model_think=(
                main_model_think
            ),
        )
    )
    route = (
        classifier_round.utterance_route
    )

    context_started_at = perf_counter()
    resolved_context = docent_resolve_context(
        None,
        text,
        route,
    )
    context_resolution_seconds = (
        perf_counter() - context_started_at
    )

    prompt_started_at = perf_counter()
    response_prompt = (
        docent_build_prompt_from_context(
            text,
            dialogue_history,
            resolved_context,
            active_branch,
        )
    )
    continuation_messages = (
        build_classifier_tool_resume_messages(
            classifier_round=(
                classifier_round
            ),
            response_prompt=response_prompt,
        )
    )
    prompt_build_seconds = (
        perf_counter() - prompt_started_at
    )

    event_stream = (
        stream_tool_aware_llm_messages(
            messages=continuation_messages,
            conversation_id=conversation_id,
            buffer_for_tool_decision=(
                route.route_type
                == "call_to_action"
            ),
            model=main_model,
            think=main_model_think,
        )
    )
    (
        model_to_first_token_seconds,
        first_token,
    ) = consume_to_first_content(
        event_stream
    )

    return {
        "success": True,
        "route": route.model_dump(
            mode="json"
        ),
        "classifier_seconds": (
            classifier_round.audit
            .classifier_execution_seconds
        ),
        "model_to_classifier_tool_seconds": (
            classifier_round.audit
            .model_to_tool_call_seconds
        ),
        "context_resolution_seconds": round(
            context_resolution_seconds,
            4,
        ),
        "prompt_build_seconds": round(
            prompt_build_seconds,
            4,
        ),
        "model_resume_to_first_token_seconds": (
            round(
                model_to_first_token_seconds,
                4,
            )
        ),
        "total_to_first_token_seconds": round(
            perf_counter()
            - total_started_at,
            4,
        ),
        "classifier_called_exactly_once": (
            classifier_round.audit
            .classifier_called_exactly_once
        ),
        "first_token": first_token,
        "context_source": (
            resolved_context.context_source
        ),
    }


def run_sample(
    *,
    mode: str,
    case: dict,
    repetition: int,
    main_model: str,
    main_model_think: bool | None,
) -> dict:
    started_at = perf_counter()

    try:
        if mode == "sequential":
            sample = (
                run_sequential_architecture(
                    case["text"],
                    main_model=main_model,
                    main_model_think=(
                        main_model_think
                    ),
                )
            )
        else:
            sample = (
                run_classifier_tool_architecture(
                    case["text"],
                    main_model=main_model,
                    main_model_think=(
                        main_model_think
                    ),
                )
            )

        result = {
            "mode": mode,
            "case_id": case["case_id"],
            "text": case["text"],
            "repetition": repetition,
            **sample,
        }
        route = result["route"]
        result[
            "classification_correct"
        ] = (
            route["route_type"]
            == case["route_type"]
            and route[
                "requires_retrieval"
            ]
            == case["requires_retrieval"]
            and route["proposed_action"]
            == case["proposed_action"]
        )
        return result
    except Exception as error:
        return {
            "mode": mode,
            "case_id": case["case_id"],
            "text": case["text"],
            "repetition": repetition,
            "success": False,
            "classification_correct": False,
            "elapsed_seconds": round(
                perf_counter() - started_at,
                4,
            ),
            "error_type": (
                type(error).__name__
            ),
            "error": str(error),
        }


def median(
    values: list[float],
) -> float:
    return round(
        statistics.median(values),
        4,
    )


def summarise_mode(
    mode: str,
    results: list[dict],
) -> dict:
    valid = [
        result
        for result in results
        if (
            result["mode"] == mode
            and result["success"]
        )
    ]
    fields = [
        "classifier_seconds",
        "context_resolution_seconds",
        "prompt_build_seconds",
        "model_resume_to_first_token_seconds",
        "total_to_first_token_seconds",
    ]
    summary = {
        "mode": mode,
        "valid_samples": len(valid),
        "correct_classifications": sum(
            result[
                "classification_correct"
            ]
            for result in valid
        ),
        "classification_accuracy": round(
            (
                sum(
                    result[
                        "classification_correct"
                    ]
                    for result in valid
                )
                / len(valid)
                if valid
                else 0.0
            ),
            4,
        ),
    }

    for field in fields:
        summary[f"median_{field}"] = median(
            [
                result[field]
                for result in valid
            ]
        )

    if mode == "classifier_tool":
        summary[
            "median_model_to_classifier_tool_seconds"
        ] = median(
            [
                result[
                    "model_to_classifier_tool_seconds"
                ]
                for result in valid
            ]
        )

    return summary


def build_paired_summary(
    results: list[dict],
) -> dict:
    pairs = []

    for case in BENCHMARK_CASES:
        for repetition in range(
            1,
            REPETITIONS + 1,
        ):
            sequential = next(
                result
                for result in results
                if (
                    result["mode"]
                    == "sequential"
                    and result["case_id"]
                    == case["case_id"]
                    and result["repetition"]
                    == repetition
                )
            )
            classifier_tool = next(
                result
                for result in results
                if (
                    result["mode"]
                    == "classifier_tool"
                    and result["case_id"]
                    == case["case_id"]
                    and result["repetition"]
                    == repetition
                )
            )

            if not (
                sequential["success"]
                and classifier_tool["success"]
            ):
                continue

            saving = (
                sequential[
                    "total_to_first_token_seconds"
                ]
                - classifier_tool[
                    "total_to_first_token_seconds"
                ]
            )
            resume_saving = (
                sequential[
                    "model_resume_to_first_token_seconds"
                ]
                - classifier_tool[
                    "model_resume_to_first_token_seconds"
                ]
            )
            pairs.append(
                {
                    "case_id": case[
                        "case_id"
                    ],
                    "repetition": repetition,
                    "sequential_seconds": (
                        sequential[
                            "total_to_first_token_seconds"
                        ]
                    ),
                    "classifier_tool_seconds": (
                        classifier_tool[
                            "total_to_first_token_seconds"
                        ]
                    ),
                    "classifier_tool_saving_seconds": (
                        round(saving, 4)
                    ),
                    "classifier_tool_faster": (
                        saving > 0
                    ),
                    "sequential_response_stage_seconds": (
                        sequential[
                            "model_resume_to_first_token_seconds"
                        ]
                    ),
                    "classifier_tool_response_stage_seconds": (
                        classifier_tool[
                            "model_resume_to_first_token_seconds"
                        ]
                    ),
                    "classifier_tool_response_stage_saving_seconds": (
                        round(
                            resume_saving,
                            4,
                        )
                    ),
                }
            )

    savings = [
        pair[
            "classifier_tool_saving_seconds"
        ]
        for pair in pairs
    ]
    resume_savings = [
        pair[
            "classifier_tool_response_stage_saving_seconds"
        ]
        for pair in pairs
    ]
    return {
        "valid_pairs": len(pairs),
        "classifier_tool_faster_pairs": sum(
            saving > 0
            for saving in savings
        ),
        "median_classifier_tool_saving_seconds": (
            median(savings)
        ),
        "mean_classifier_tool_saving_seconds": (
            round(
                statistics.mean(savings),
                4,
            )
        ),
        "classifier_tool_response_stage_faster_pairs": (
            sum(
                saving > 0
                for saving in resume_savings
            )
        ),
        "median_classifier_tool_response_stage_saving_seconds": (
            median(resume_savings)
        ),
        "mean_classifier_tool_response_stage_saving_seconds": (
            round(
                statistics.mean(
                    resume_savings
                ),
                4,
            )
        ),
        "pairs": pairs,
    }


def build_case_summaries(
    results: list[dict],
) -> list[dict]:
    summaries = []

    for case in BENCHMARK_CASES:
        row = {
            "case_id": case["case_id"],
        }

        for mode in [
            "sequential",
            "classifier_tool",
        ]:
            samples = [
                result
                for result in results
                if (
                    result["success"]
                    and result["case_id"]
                    == case["case_id"]
                    and result["mode"]
                    == mode
                )
            ]
            row[mode] = {
                "median_total_to_first_token_seconds": (
                    median(
                        [
                            sample[
                                "total_to_first_token_seconds"
                            ]
                            for sample
                            in samples
                        ]
                    )
                ),
                "median_response_stage_seconds": (
                    median(
                        [
                            sample[
                                "model_resume_to_first_token_seconds"
                            ]
                            for sample
                            in samples
                        ]
                    )
                ),
                "median_classifier_seconds": (
                    median(
                        [
                            sample[
                                "classifier_seconds"
                            ]
                            for sample
                            in samples
                        ]
                    )
                ),
            }

            if mode == "classifier_tool":
                row[mode][
                    "median_model_to_classifier_tool_seconds"
                ] = median(
                    [
                        sample[
                            "model_to_classifier_tool_seconds"
                        ]
                        for sample
                        in samples
                    ]
                )

        summaries.append(row)

    return summaries


def write_markdown(
    path: Path,
    report: dict,
) -> None:
    sequential = report["summaries"][
        "sequential"
    ]
    classifier_tool = report["summaries"][
        "classifier_tool"
    ]
    paired = report["paired_summary"]
    lines = [
        "# Sequential vs classifier-tool architecture",
        "",
        (
            "Boundary: finalized text request to "
            "the first non-empty main-model "
            "response token."
        ),
        "",
        (
            "Sequential uses the separate configured "
            "utterance-classifier model, then starts a "
            "fresh main-model response request. The "
            "classifier-tool architecture asks the main "
            "model itself to provide classification fields "
            "as mandatory tool arguments, validates them "
            "locally without another model request, and "
            "resumes that same main-model conversation."
        ),
        "",
        "| Median interval | Sequential | Classifier tool |",
        "|---|---:|---:|",
        (
            "| Main model → classifier tool call "
            "| n/a | "
            f"{classifier_tool['median_model_to_classifier_tool_seconds']:.4f}s |"
        ),
        (
            "| Separate classifier / tool validation | "
            f"{sequential['median_classifier_seconds']:.4f}s | "
            f"{classifier_tool['median_classifier_seconds']:.4f}s |"
        ),
        (
            "| Context resolution | "
            f"{sequential['median_context_resolution_seconds']:.4f}s | "
            f"{classifier_tool['median_context_resolution_seconds']:.4f}s |"
        ),
        (
            "| Main model start/resume → first token | "
            f"{sequential['median_model_resume_to_first_token_seconds']:.4f}s | "
            f"{classifier_tool['median_model_resume_to_first_token_seconds']:.4f}s |"
        ),
        (
            "| **Total → first token** | "
            f"**{sequential['median_total_to_first_token_seconds']:.4f}s** | "
            f"**{classifier_tool['median_total_to_first_token_seconds']:.4f}s** |"
        ),
        "",
        (
            f"Classifier-tool was faster in "
            f"{paired['classifier_tool_faster_pairs']}/"
            f"{paired['valid_pairs']} paired samples."
        ),
        (
            "Median classifier-tool saving: "
            f"{paired['median_classifier_tool_saving_seconds']:.4f}s."
        ),
        (
            "The resumed response stage was faster "
            f"in {paired['classifier_tool_response_stage_faster_pairs']}/"
            f"{paired['valid_pairs']} pairs, with "
            "a median saving of "
            f"{paired['median_classifier_tool_response_stage_saving_seconds']:.4f}s."
        ),
        (
            "Classification accuracy: "
            f"sequential {sequential['correct_classifications']}/"
            f"{sequential['valid_samples']} "
            f"({sequential['classification_accuracy']:.1%}); "
            "classifier-tool "
            f"{classifier_tool['correct_classifications']}/"
            f"{classifier_tool['valid_samples']} "
            f"({classifier_tool['classification_accuracy']:.1%})."
        ),
        "",
        "## Per-case medians",
        "",
        "| Case | Sequential total | Tool total | Sequential response stage | Tool response stage |",
        "|---|---:|---:|---:|---:|",
    ]

    for case in report["case_summaries"]:
        sequential_case = case[
            "sequential"
        ]
        tool_case = case[
            "classifier_tool"
        ]
        lines.append(
            f"| {case['case_id']} | "
            f"{sequential_case['median_total_to_first_token_seconds']:.4f}s | "
            f"{tool_case['median_total_to_first_token_seconds']:.4f}s | "
            f"{sequential_case['median_response_stage_seconds']:.4f}s | "
            f"{tool_case['median_response_stage_seconds']:.4f}s |"
        )

    overall_winner = (
        "classifier-tool"
        if paired[
            "median_classifier_tool_saving_seconds"
        ] > 0
        else "sequential"
    )
    response_winner = (
        "classifier-tool"
        if paired[
            "median_classifier_tool_response_stage_saving_seconds"
        ] > 0
        else "sequential"
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                f"The {overall_winner} architecture had "
                "the lower paired median end-to-end time "
                "to the first response token in this run."
            ),
            (
                f"The {response_winner} architecture had "
                "the lower paired median response-stage "
                "latency. This isolates whether reusing the "
                "main model's classification conversation "
                "helped its subsequent response begin."
            ),
            (
                "Latency and classification accuracy must "
                "be considered together; a faster invalid "
                "classification is not a successful sample."
            ),
        ]
    )
    lines.extend(
        [
        "",
        "## Paired samples",
        "",
        "| Case | Run | Sequential | Classifier tool | Tool saving |",
        "|---|---:|---:|---:|---:|",
        ]
    )

    for pair in paired["pairs"]:
        lines.append(
            f"| {pair['case_id']} | "
            f"{pair['repetition']} | "
            f"{pair['sequential_seconds']:.4f}s | "
            f"{pair['classifier_tool_seconds']:.4f}s | "
            f"{pair['classifier_tool_saving_seconds']:.4f}s |"
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
            "classifier_architecture_"
            "gemma4_think_false.json"
        ),
    )
    parser.add_argument(
        "--model",
        default="gemma4:cloud",
    )
    parser.add_argument(
        "--think",
        choices=[
            "false",
            "true",
            "default",
        ],
        default="false",
    )
    arguments = parser.parse_args()
    main_model_think = {
        "false": False,
        "true": True,
        "default": None,
    }[arguments.think]
    results = []
    total_samples = (
        len(BENCHMARK_CASES)
        * REPETITIONS
        * 2
    )
    sample_index = 0

    for repetition in range(
        1,
        REPETITIONS + 1,
    ):
        for case_index, case in enumerate(
            BENCHMARK_CASES
        ):
            modes = (
                [
                    "sequential",
                    "classifier_tool",
                ]
                if (
                    (
                        repetition
                        + case_index
                    )
                    % 2
                    == 0
                )
                else [
                    "classifier_tool",
                    "sequential",
                ]
            )

            for mode in modes:
                sample_index += 1
                print(
                    f"{sample_index:02d}/"
                    f"{total_samples} "
                    f"{mode} "
                    f"{case['case_id']} "
                    f"run={repetition}",
                    flush=True,
                )
                result = run_sample(
                    mode=mode,
                    case=case,
                    repetition=repetition,
                    main_model=arguments.model,
                    main_model_think=(
                        main_model_think
                    ),
                )
                results.append(result)
                print(
                    json.dumps(
                        {
                            "success": result[
                                "success"
                            ],
                            "total_to_first_token_seconds": (
                                result.get(
                                    "total_to_first_token_seconds"
                                )
                            ),
                            "model_resume_to_first_token_seconds": (
                                result.get(
                                    "model_resume_to_first_token_seconds"
                                )
                            ),
                            "error": result.get(
                                "error"
                            ),
                        },
                        indent=2,
                    ),
                    flush=True,
                )

    summaries = {
        mode: summarise_mode(
            mode,
            results,
        )
        for mode in [
            "sequential",
            "classifier_tool",
        ]
    }
    paired_summary = build_paired_summary(
        results
    )
    case_summaries = build_case_summaries(
        results
    )
    report = {
        "main_model": arguments.model,
        "main_model_think": (
            main_model_think
        ),
        "main_model_streaming": True,
        "architectures": {
            "sequential": (
                "Separate Gemma utterance "
                "classifier, then a fresh main-"
                "model response request."
            ),
            "classifier_tool": (
                "Main model supplies the "
                "classification as mandatory "
                "tool arguments; backend validates "
                "without a classifier-model call, "
                "then resumes the same main-model "
                "conversation."
            ),
        },
        "boundary": (
            "finalized_text_request_to_first_"
            "main_model_response_token"
        ),
        "case_count": len(BENCHMARK_CASES),
        "repetitions": REPETITIONS,
        "sample_count": len(results),
        "summaries": summaries,
        "paired_summary": paired_summary,
        "case_summaries": case_summaries,
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
            {
                "summaries": summaries,
                "paired_summary": {
                    key: value
                    for key, value
                    in paired_summary.items()
                    if key != "pairs"
                },
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
