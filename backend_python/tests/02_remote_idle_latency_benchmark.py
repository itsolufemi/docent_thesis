"""Measure latency after a genuine idle period of the remote provider.

This experiment is intentionally session-based. Start one session only after
Docent/Ollama has been unused for the chosen idle period, then repeat the same
command after a new idle period. The script never sends warm-up requests and
keeps resolver and main-LLM sessions separate so one path cannot warm the
other.

Resolver session (the recommended first phase)::

    ..\\venv\\Scripts\\python.exe 02_remote_idle_latency_benchmark.py \
        --endpoint resolver --session 1 --idle-minutes 60

Main-LLM session::

    ..\\venv\\Scripts\\python.exe 02_remote_idle_latency_benchmark.py \
        --endpoint main --session 1 --idle-minutes 60

After several sessions, print position means::

    ..\\venv\\Scripts\\python.exe 02_remote_idle_latency_benchmark.py \
        --endpoint resolver --summary

The claimed idle duration is recorded for auditability; the script cannot
prove that a remote cloud model was unloaded.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend_python"
CONTROL_PATH = HERE / "00_context_resolver_benchmark.py"

for import_root in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def load_control_module():
    spec = importlib.util.spec_from_file_location(
        "context_resolver_control_benchmark",
        CONTROL_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load control benchmark: {CONTROL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTROL = load_control_module()

CSV_FIELDS = [
    "session",
    "endpoint_kind",
    "idle_minutes_claimed",
    "position",
    "timestamp",
    "model",
    "endpoint",
    "prompt_chars",
    "prompt_sha256",
    "wall_clock_seconds",
    "request_to_response_headers_seconds",
    "request_to_first_chunk_seconds",
    "request_to_first_content_token_seconds",
    "full_generation_seconds",
    "provider_total_duration",
    "provider_load_duration",
    "provider_prompt_eval_duration",
    "provider_eval_duration",
    "provider_total_duration_seconds",
    "provider_load_duration_seconds",
    "provider_prompt_eval_duration_seconds",
    "provider_eval_duration_seconds",
    "result",
    "error",
]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_stem(endpoint_kind: str, output_dir: Path) -> Path:
    return output_dir / f"02_remote_idle_{endpoint_kind}_results"


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as jsonl_file:
        for line in jsonl_file:
            if line.strip():
                records.append(json.loads(line))
    return records


def write_session_records(
    records: list[dict[str, Any]],
    *,
    endpoint_kind: str,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(endpoint_kind, output_dir)
    jsonl_path = stem.with_suffix(".jsonl")
    csv_path = stem.with_suffix(".csv")

    with jsonl_path.open("a", encoding="utf-8") as jsonl_file:
        for record in records:
            jsonl_file.write(
                json.dumps(record, ensure_ascii=False, default=str) + "\n"
            )

    csv_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )
        if not csv_exists:
            writer.writeheader()
        writer.writerows(records)

    return jsonl_path, csv_path


def run_session(args: argparse.Namespace) -> int:
    prompts = CONTROL.build_frozen_prompts(args.user_input)
    think = CONTROL.parse_think(args.main_think)
    prompt = prompts.resolver if args.endpoint == "resolver" else prompts.main
    client = CONTROL.create_client(args.base_url, args.timeout)
    records: list[dict[str, Any]] = []

    try:
        for position in range(1, args.requests + 1):
            if args.endpoint == "resolver":
                record = CONTROL.run_resolver_request(
                    client,
                    phase="measured",
                    client_mode="persistent",
                    run=position,
                    model=args.model,
                    prompt=prompt,
                )
            else:
                record = CONTROL.run_main_request(
                    client,
                    phase="measured",
                    client_mode="persistent",
                    run=position,
                    model=args.model,
                    prompt=prompt,
                    think=think,
                )

            record.update(
                {
                    "session": args.session,
                    "endpoint_kind": args.endpoint,
                    "idle_minutes_claimed": args.idle_minutes,
                    "position": position,
                }
            )
            records.append(record)
            wall = record.get("wall_clock_seconds")
            error = record.get("error")
            print(
                f"session={args.session} position={position:02d} "
                f"endpoint={args.endpoint} wall={wall}s"
                + (f" ERROR={error}" if error else "")
            )
    finally:
        client.close()

    jsonl_path, csv_path = write_session_records(
        records,
        endpoint_kind=args.endpoint,
        output_dir=args.output_dir,
    )
    print(f"JSONL: {jsonl_path}")
    print(f"CSV:   {csv_path}")
    if args.idle_minutes is None:
        print(
            "WARNING: --idle-minutes was not supplied; the run is retained "
            "but its idle duration is unverified."
        )
    return 1 if any(record.get("error") for record in records) else 0


def summary(args: argparse.Namespace) -> int:
    jsonl_path = output_stem(args.endpoint, args.output_dir).with_suffix(".jsonl")
    records = load_records(jsonl_path)
    if not records:
        print(f"No records found at {jsonl_path}")
        return 1

    print(f"Endpoint: {args.endpoint}")
    print(f"Records: {len(records)} across sessions")
    sessions = sorted({int(record["session"]) for record in records})

    def print_metric(field: str, label: str) -> None:
        print(f"\n{label}")
        headings = ["position"] + [f"S{session}" for session in sessions] + ["mean"]
        print(" | ".join(f"{heading:>9}" for heading in headings))
        print("-|-".join("---------" for _ in headings))
        for position in range(1, args.requests + 1):
            values_by_session: list[list[float]] = []
            for session in sessions:
                values_by_session.append(
                    [
                        float(record[field])
                        for record in records
                        if int(record.get("session", 0)) == session
                        and int(record.get("position", 0)) == position
                        and record.get(field) not in (None, "")
                        and not record.get("error")
                    ]
                )
            flattened = [value for values in values_by_session for value in values]
            cells = [
                f"{statistics.mean(values):.3f}" if values else "n/a"
                for values in values_by_session
            ]
            cells.append(f"{statistics.mean(flattened):.3f}" if flattened else "n/a")
            print(" | ".join([f"{position:>9}"] + [f"{cell:>9}" for cell in cells]))

    print_metric("wall_clock_seconds", "Wall-clock seconds")
    if args.endpoint == "resolver":
        print_metric("provider_total_duration_seconds", "Provider total_duration seconds")
    else:
        print_metric(
            "request_to_first_content_token_seconds",
            "Main first-content-token seconds",
        )
        print_metric("full_generation_seconds", "Main full-generation seconds")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or summarize the remote-idle/provider-state experiment."
    )
    parser.add_argument("--endpoint", choices=("resolver", "main"), default="resolver")
    parser.add_argument("--session", type=int, help="1-based idle session number")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--idle-minutes", type=float, default=None)
    parser.add_argument("--user-input", default="Hello?")
    parser.add_argument("--model", default=CONTROL.settings.ollama_model)
    parser.add_argument("--base-url", default=CONTROL.settings.ollama_base_url)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--main-think", choices=("config", "true", "false"), default="config")
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.requests < 1:
        parser.error("--requests must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.summary:
        return args
    if args.session is None or args.session < 1:
        parser.error("--session must be a positive integer for a measured session")
    if args.idle_minutes is not None and args.idle_minutes < 0:
        parser.error("--idle-minutes cannot be negative")
    return args


def main() -> int:
    args = parse_args()
    if args.summary:
        return summary(args)
    return run_session(args)


if __name__ == "__main__":
    raise SystemExit(main())
