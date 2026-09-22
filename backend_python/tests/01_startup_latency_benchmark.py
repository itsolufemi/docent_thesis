"""Measure repeated request positions across fresh Python processes.

This is the startup/warm-state experiment that follows the steady-state
control in ``00_context_resolver_benchmark.py``. Each cycle launches a child
process, performs ten identical resolver/main pairs with no warm-up calls, and
then exits the child before the next cycle starts. Remote Ollama state is not
reset by this experiment.

Run with the backend virtual environment:

    ..\\venv\\Scripts\\python.exe 01_startup_latency_benchmark.py
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend_python"
CONTROL_PATH = HERE / "00_context_resolver_benchmark.py"

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def load_control_module():
    spec = importlib.util.spec_from_file_location(
        "context_resolver_control_benchmark",
        CONTROL_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load control benchmark: {CONTROL_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses (used by the control benchmark) resolve the defining module
    # through sys.modules while decorating classes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTROL = load_control_module()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_worker(args: argparse.Namespace) -> int:
    """Execute one cycle and emit only JSON records on stdout."""
    prompts = CONTROL.build_frozen_prompts(args.user_input)
    think = CONTROL.parse_think(args.main_think)
    client = CONTROL.create_client(args.base_url, args.timeout)

    try:
        for position in range(1, args.positions + 1):
            for endpoint in ("resolver", "main"):
                if endpoint == "resolver":
                    record = CONTROL.run_resolver_request(
                        client,
                        phase="measured",
                        client_mode="persistent",
                        run=position,
                        model=args.model,
                        prompt=prompts.resolver,
                    )
                else:
                    record = CONTROL.run_main_request(
                        client,
                        phase="measured",
                        client_mode="persistent",
                        run=position,
                        model=args.model,
                        prompt=prompts.main,
                        think=think,
                    )

                record["cycle"] = args.cycle
                record["position"] = position
                record["process_pid"] = os.getpid()
                print(
                    json.dumps(record, ensure_ascii=False, default=str),
                    flush=True,
                )
    finally:
        client.close()

    return 0


def run_cycle(args: argparse.Namespace, cycle: int) -> list[dict[str, Any]]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--cycle",
        str(cycle),
        "--positions",
        str(args.positions),
        "--user-input",
        args.user_input,
        "--model",
        args.model,
        "--base-url",
        args.base_url,
        "--timeout",
        str(args.timeout),
        "--main-think",
        args.main_think,
    ]
    worker_environment = os.environ.copy()
    worker_environment["PYTHONUNBUFFERED"] = "1"
    worker_environment["PYTHONPATH"] = os.pathsep.join(
        str(path)
        for path in (REPOSITORY_ROOT, BACKEND_ROOT)
    )

    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=worker_environment,
        capture_output=True,
        text=True,
        timeout=max(60.0, args.timeout * args.positions * 4),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Cycle {cycle} child exited {completed.returncode}.\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )

    records: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Cycle {cycle} emitted non-JSON output: {line!r}"
            ) from error

    expected = args.positions * 2
    if len(records) != expected:
        raise RuntimeError(
            f"Cycle {cycle} emitted {len(records)} records; expected {expected}. "
            f"stderr:\n{completed.stderr[-4000:]}"
        )
    return records


def write_results(
    records: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
) -> tuple[Path, Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = HERE / f"01_startup_latency_benchmark_results_{timestamp}"
    jsonl_path = stem.with_suffix(".jsonl")
    csv_path = stem.with_suffix(".csv")
    metadata_path = stem.with_name(stem.name + "_metadata.json")

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        for record in records:
            jsonl_file.write(
                json.dumps(record, ensure_ascii=False, default=str) + "\n"
            )

    control_fields = [
        field
        for field in CONTROL.CSV_FIELDS
        if field not in {"phase", "client_mode", "run"}
    ]
    csv_fields = ["cycle", "position", "process_pid"] + control_fields
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=csv_fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    metadata_path.write_text(
        json.dumps(
            {
                "created_at": utc_timestamp(),
                "experiment": "fresh-process/startup latency",
                "cycles": args.cycles,
                "positions_per_cycle": args.positions,
                "warmups_per_cycle": 0,
                "client_mode": "persistent within each child process",
                "model": args.model,
                "base_url": args.base_url.rstrip("/"),
                "main_think": CONTROL.parse_think(args.main_think),
                "user_input": args.user_input,
                "resolver_prompt": CONTROL.build_frozen_prompts(
                    args.user_input
                ).resolver,
                "main_prompt": CONTROL.build_frozen_prompts(
                    args.user_input
                ).main,
                "remote_provider_reset": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return jsonl_path, csv_path, metadata_path


def print_position_summary(records: list[dict[str, Any]], positions: int) -> None:
    print("\nPosition means across cycles")
    print("position | resolver wall | resolver provider | main TTFT | main full")
    print("---------|---------------|-------------------|-----------|----------")

    for position in range(1, positions + 1):
        resolver = [
            float(record["wall_clock_seconds"])
            for record in records
            if record.get("endpoint") == "/api/generate"
            and int(record.get("position", 0)) == position
            and not record.get("error")
        ]
        resolver_provider = [
            float(record["provider_total_duration_seconds"])
            for record in records
            if record.get("endpoint") == "/api/generate"
            and int(record.get("position", 0)) == position
            and record.get("provider_total_duration_seconds") not in (None, "")
        ]
        main_ttft = [
            float(record["request_to_first_content_token_seconds"])
            for record in records
            if record.get("endpoint") == "/api/chat"
            and int(record.get("position", 0)) == position
            and record.get("request_to_first_content_token_seconds") not in (None, "")
        ]
        main_full = [
            float(record["full_generation_seconds"])
            for record in records
            if record.get("endpoint") == "/api/chat"
            and int(record.get("position", 0)) == position
            and not record.get("error")
        ]

        def mean(values: list[float]) -> str:
            return f"{statistics.mean(values):.3f}" if values else "n/a"

        print(
            f"{position:>8} | {mean(resolver):>13} | "
            f"{mean(resolver_provider):>17} | {mean(main_ttft):>9} | "
            f"{mean(main_full):>8}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run identical resolver/main request pairs from fresh Python "
            "processes with no startup warm-up calls."
        )
    )
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--positions", type=int, default=10)
    parser.add_argument("--user-input", default="Hello?")
    parser.add_argument("--model", default=CONTROL.settings.ollama_model)
    parser.add_argument("--base-url", default=CONTROL.settings.ollama_base_url)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--main-think",
        choices=("config", "true", "false"),
        default="config",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cycle", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.cycles < 1 or args.positions < 1:
        parser.error("--cycles and --positions must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.worker and args.cycle < 1:
        parser.error("--cycle is required for worker mode")
    return args


def main() -> int:
    args = parse_args()
    if args.worker:
        return run_worker(args)

    total_requests = args.cycles * args.positions * 2
    print(
        f"Starting {args.cycles} fresh-process cycles, "
        f"{args.positions} pairs each ({total_requests} requests total)."
    )
    print("No warm-up requests will be sent; one persistent client is used per cycle.")
    records: list[dict[str, Any]] = []
    for cycle in range(1, args.cycles + 1):
        cycle_records = run_cycle(args, cycle)
        records.extend(cycle_records)
        failures = sum(bool(record.get("error")) for record in cycle_records)
        print(f"cycle {cycle:02d}/{args.cycles}: {len(cycle_records)} records, {failures} errors")

    jsonl_path, csv_path, metadata_path = write_results(records, args=args)
    print_position_summary(records, args.positions)
    print(f"JSONL:    {jsonl_path}")
    print(f"CSV:      {csv_path}")
    print(f"Metadata: {metadata_path}")
    return 1 if any(record.get("error") for record in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
