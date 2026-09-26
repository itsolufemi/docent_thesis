r"""Compare resolver-based and direct-routing Docent query pipelines.

This is a backend pipeline benchmark. It begins after transcription has
finalised and ends when response generation completes, so browser playback
and TTS timings intentionally remain outside its scope.

Examples::

    ..\venv\Scripts\python.exe 05_direct_routing_comparison_benchmark.py \
        --pairs 5

    ..\venv\Scripts\python.exe 05_direct_routing_comparison_benchmark.py \
        --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend_python"

for import_root in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from conversation_core.memory.conversation_store import (  # noqa: E402
    add_dialogue_turn,
    conversations,
    create_conversation,
)
from conversation_core.schemas.llm_stream_schemas import (  # noqa: E402
    LLMStreamEvent,
)
from conversation_core.services.query_service import QueryEngine  # noqa: E402
from docent.services.docent_query_service import (  # noqa: E402
    context_resolved_docent_query_engine,
    direct_docent_query_engine,
)


CSV_FIELDS = (
    "timestamp",
    "pair",
    "order",
    "architecture",
    "scenario",
    "utterance",
    "wall_clock_seconds",
    "context_resolution_seconds",
    "pre_llm_total_seconds",
    "first_model_activity_seconds",
    "control_detection_seconds",
    "tool_call_start_seconds",
    "retrieval_complete_seconds",
    "first_visitor_delta_seconds",
    "response_complete_seconds",
    "route_type",
    "response_characters",
    "subjects",
    "references",
    "source_count",
    "error",
)


@dataclass(frozen=True)
class HistoryTurn:
    user: str
    assistant: str
    subjects: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    name: str
    utterance: str
    history: tuple[HistoryTurn, ...] = ()


SCENARIOS = (
    Scenario(
        name="normal",
        utterance="Hello.",
    ),
    Scenario(
        name="retrieval",
        utterance="Who painted The Swing?",
    ),
    Scenario(
        name="reference_resolution",
        utterance="Who painted it?",
        history=(
            HistoryTurn(
                user="Tell me about The Swing.",
                assistant="It is a celebrated Rococo painting.",
                subjects=("The Swing",),
                references=("painting:581",),
            ),
        ),
    ),
    Scenario(
        name="comparison",
        utterance="How is The Swing different from The Arab Tent?",
    ),
    Scenario(
        name="backchannel",
        utterance="Mm-hm.",
        history=(
            HistoryTurn(
                user="Tell me about The Swing.",
                assistant="The scene is playful and deliberately theatrical.",
                subjects=("The Swing",),
                references=("painting:581",),
            ),
        ),
    ),
)


class ResultWriter:
    def __init__(self, output_stem: Path) -> None:
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path = output_stem.with_suffix(".csv")
        self.jsonl_path = output_stem.with_suffix(".jsonl")
        self._csv_file = self.csv_path.open(
            "w",
            encoding="utf-8",
            newline="",
        )
        self._jsonl_file = self.jsonl_path.open("w", encoding="utf-8")
        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )
        self._csv_writer.writeheader()

    def write(self, record: dict[str, Any]) -> None:
        csv_record = dict(record)
        for field in ("subjects", "references"):
            csv_record[field] = json.dumps(record.get(field, []))

        self._csv_writer.writerow(csv_record)
        self._csv_file.flush()
        self._jsonl_file.write(
            json.dumps(record, ensure_ascii=False, default=str) + "\n"
        )
        self._jsonl_file.flush()

    def close(self) -> None:
        self._csv_file.close()
        self._jsonl_file.close()

    def __enter__(self) -> ResultWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _output_stem(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"05_direct_routing_comparison_results_{timestamp}"


def _prepare_conversation(scenario: Scenario) -> str:
    state = create_conversation()

    for index, history_turn in enumerate(scenario.history, start=1):
        add_dialogue_turn(
            state.conversation_id,
            request_id=f"history-{index}",
            user=history_turn.user,
            assistant=history_turn.assistant,
            subject=list(history_turn.subjects),
            reference=list(history_turn.references),
        )

    return state.conversation_id


def run_once(
    *,
    architecture: str,
    engine: QueryEngine,
    scenario: Scenario,
    pair: int,
    order: int,
) -> dict[str, Any]:
    conversation_id = _prepare_conversation(scenario)
    started_at = perf_counter()
    relative_events: dict[str, float] = {}
    timing_events: list[dict[str, Any]] = []
    control_route_type: str | None = None

    def elapsed() -> float:
        return round(perf_counter() - started_at, 6)

    def capture_once(name: str) -> None:
        relative_events.setdefault(name, elapsed())

    def on_stream_event(event: LLMStreamEvent) -> None:
        nonlocal control_route_type

        if event.event_type == "timing":
            timing_events.append(
                {
                    "name": event.timing_name,
                    "seconds": event.timing_seconds,
                    **event.timing_payload,
                }
            )
            return

        if event.event_type in {
            "content_delta",
            "control_signal",
            "tool_call",
        }:
            capture_once("first_model_activity_seconds")

        if event.event_type == "content_delta":
            capture_once("first_visitor_delta_seconds")
        elif event.event_type == "control_signal":
            capture_once("control_detection_seconds")
            if event.control_signal is not None:
                control_route_type = event.control_signal.route_type
        elif event.event_type == "tool_call":
            capture_once("tool_call_start_seconds")
        elif event.event_type == "tool_result":
            capture_once("retrieval_complete_seconds")
        elif event.event_type == "response_complete":
            capture_once("response_complete_seconds")

    error = ""
    result = None

    try:
        result = engine.generate_streaming_response(
            scenario.utterance,
            conversation_id=conversation_id,
            request_id=(
                f"benchmark-{pair}-{architecture}-{scenario.name}"
            ),
            include_debug=True,
            on_stream_event=on_stream_event,
        )
    except Exception as exception:  # keep the paired run recoverable
        error = f"{type(exception).__name__}: {exception}"

    wall_clock_seconds = elapsed()
    state = conversations.get(conversation_id)
    turn = (
        state.dialogue_history[-1]
        if state is not None and state.dialogue_history
        else None
    )
    timing_by_name = {
        item["name"]: item["seconds"]
        for item in timing_events
        if item.get("name")
    }

    record = {
        "timestamp": _timestamp(),
        "pair": pair,
        "order": order,
        "architecture": architecture,
        "scenario": scenario.name,
        "utterance": scenario.utterance,
        "wall_clock_seconds": wall_clock_seconds,
        "context_resolution_seconds": timing_by_name.get(
            "context_resolution_seconds"
        ),
        "pre_llm_total_seconds": timing_by_name.get(
            "pre_llm_total_seconds"
        ),
        "first_model_activity_seconds": relative_events.get(
            "first_model_activity_seconds"
        ),
        "control_detection_seconds": relative_events.get(
            "control_detection_seconds"
        ),
        "tool_call_start_seconds": relative_events.get(
            "tool_call_start_seconds"
        ),
        "retrieval_complete_seconds": relative_events.get(
            "retrieval_complete_seconds"
        ),
        "first_visitor_delta_seconds": relative_events.get(
            "first_visitor_delta_seconds"
        ),
        "response_complete_seconds": relative_events.get(
            "response_complete_seconds"
        ),
        "route_type": (
            control_route_type
            or (turn.route_type if turn is not None else None)
        ),
        "response_characters": (
            len(result.response) if result is not None else 0
        ),
        "subjects": turn.subject if turn is not None else [],
        "references": turn.reference if turn is not None else [],
        "source_count": len(result.sources) if result is not None else 0,
        "error": error,
        "timing_events": timing_events,
    }

    conversations.pop(conversation_id, None)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the resolver-based and direct-routing Docent pipelines."
        )
    )
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[scenario.name for scenario in SCENARIOS],
        help="Run only the named scenario; may be supplied more than once.",
    )
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.pairs < 1:
        parser.error("--pairs must be at least one")

    return args


def main() -> int:
    args = parse_args()
    selected = [
        scenario
        for scenario in SCENARIOS
        if not args.scenario or scenario.name in args.scenario
    ]

    print("Direct-routing comparison benchmark")
    print(f"Pairs: {args.pairs}")
    print("Scenarios: " + ", ".join(item.name for item in selected))

    if args.dry_run:
        print("Dry run: no model requests were made.")
        return 0

    output_stem = _output_stem(args.output_dir)
    engines = {
        "resolver": context_resolved_docent_query_engine,
        "direct": direct_docent_query_engine,
    }

    with ResultWriter(output_stem) as writer:
        for pair in range(1, args.pairs + 1):
            architecture_order = (
                ("resolver", "direct")
                if pair % 2 == 1
                else ("direct", "resolver")
            )

            for scenario in selected:
                for order, architecture in enumerate(
                    architecture_order,
                    start=1,
                ):
                    record = run_once(
                        architecture=architecture,
                        engine=engines[architecture],
                        scenario=scenario,
                        pair=pair,
                        order=order,
                    )
                    writer.write(record)
                    print(
                        f"pair={pair} scenario={scenario.name} "
                        f"architecture={architecture} "
                        f"wall={record['wall_clock_seconds']:.4f}s "
                        f"error={record['error'] or '-'}"
                    )

    print(f"CSV: {output_stem.with_suffix('.csv')}")
    print(f"JSONL: {output_stem.with_suffix('.jsonl')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
