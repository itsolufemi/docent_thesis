"""Measure resolver latency after Ollama is stopped for the whole idle period.

This is a local full-system cold-start condition, distinct from Experiment 02.
The controller stops ``ollama.exe``, verifies both that the process is absent
and that the configured TCP port is closed throughout the idle interval, then
starts ``ollama serve``. It polls only Ollama's local ``/api/version`` endpoint
until the gateway is ready and immediately sends the measured requests. The
readiness probe does not contact ``gemma4:cloud``.

The controller Python process necessarily remains alive to keep time and audit
the shutdown. It creates no Ollama HTTP client until after the restart.

Example::

    ..\\venv\\Scripts\\python.exe 03_full_system_cold_start_benchmark.py \\
        --endpoint resolver --session 1 --idle-minutes 10
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend_python"
CONTROL_PATH = HERE / "00_context_resolver_benchmark.py"

for import_root in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def load_control_module():
    spec = importlib.util.spec_from_file_location(
        "context_resolver_control_benchmark_for_cold_start",
        CONTROL_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load control benchmark: {CONTROL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTROL = load_control_module()

OLLAMA_IMAGE_NAMES = ("ollama app.exe", "ollama.exe", "llama-server.exe")

EXPERIMENT_FIELDS = [
    "session",
    "endpoint_kind",
    "idle_minutes_claimed",
    "position",
    "cold_start_mode",
    "controller_pid",
    "ollama_pid",
    "idle_started_at",
    "idle_completed_at",
    "restart_started_at",
    "ollama_ready_at",
    "ollama_ready_seconds",
]
CONTROL_FIELDS = [
    field
    for field in CONTROL.CSV_FIELDS
    if field not in {"phase", "client_mode", "run"}
]
CSV_FIELDS = EXPERIMENT_FIELDS + CONTROL_FIELDS


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_stem(endpoint_kind: str, output_dir: Path) -> Path:
    return output_dir / f"03_full_system_cold_start_{endpoint_kind}_results"


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def parse_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Unsupported Ollama base URL: {base_url!r}")
    default_port = 443 if parsed.scheme == "https" else 80
    return parsed.hostname, parsed.port or default_port


def port_is_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ollama_process_running() -> bool:
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    process_listing = completed.stdout.lower()
    return any(f'"{name}"' in process_listing for name in OLLAMA_IMAGE_NAMES)


def stop_ollama() -> None:
    # Stop the desktop supervisor first; otherwise it immediately relaunches
    # ollama.exe. The inference worker is included so the audit covers every
    # local Ollama component, not only the HTTP gateway.
    for image_name in OLLAMA_IMAGE_NAMES:
        completed = subprocess.run(
            ["taskkill", "/IM", image_name, "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode not in {0, 128}:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"Could not stop {image_name}: {detail}")


def wait_for_shutdown(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not ollama_process_running() and not port_is_open(host, port):
            return
        time.sleep(0.25)
    raise RuntimeError(
        "Ollama did not fully stop: its process or configured port remains live."
    )


def audit_idle(host: str, port: int, idle_minutes: float) -> tuple[str, str]:
    started_at = utc_timestamp()
    duration = idle_minutes * 60.0
    started = time.monotonic()
    deadline = started + duration
    next_report = started + 60.0

    while time.monotonic() < deadline:
        if ollama_process_running() or port_is_open(host, port):
            raise RuntimeError(
                "Ollama became live during the idle interval; run is invalid."
            )
        now = time.monotonic()
        if now >= next_report:
            elapsed_minutes = min(idle_minutes, (now - started) / 60.0)
            print(f"idle_elapsed_minutes={elapsed_minutes:.1f}", flush=True)
            next_report += 60.0
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))

    if ollama_process_running() or port_is_open(host, port):
        raise RuntimeError("Ollama was live at the end of the idle interval.")
    return started_at, utc_timestamp()


def start_ollama(executable: Path, log_path: Path) -> tuple[subprocess.Popen, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("ab")
    try:
        process = subprocess.Popen(
            [str(executable), "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        log_file.close()
    return process, utc_timestamp()


def wait_for_ready(base_url: str, process: subprocess.Popen, timeout: float) -> float:
    started = time.perf_counter()
    deadline = time.monotonic() + timeout
    url = base_url.rstrip("/") + "/api/version"
    last_error = "no response"

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Ollama exited during startup with {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    return round(time.perf_counter() - started, 6)
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
        time.sleep(0.1)
    raise RuntimeError(f"Ollama was not ready within {timeout}s: {last_error}")


def write_records(
    records: list[dict[str, Any]], endpoint_kind: str, output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(endpoint_kind, output_dir)
    jsonl_path = stem.with_suffix(".jsonl")
    csv_path = stem.with_suffix(".csv")

    with jsonl_path.open("a", encoding="utf-8") as target:
        for record in records:
            target.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    csv_exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not csv_exists:
            writer.writeheader()
        writer.writerows(records)
    return jsonl_path, csv_path


def run(args: argparse.Namespace) -> int:
    jsonl_path = output_stem(args.endpoint, args.output_dir).with_suffix(".jsonl")
    existing = load_records(jsonl_path)
    if any(int(record.get("session", 0)) == args.session for record in existing):
        raise RuntimeError(f"Session {args.session} already exists in {jsonl_path}")

    host, port = parse_host_port(args.base_url)
    print("Stopping Ollama...", flush=True)
    stop_ollama()
    wait_for_shutdown(host, port)
    print(f"Ollama stopped; beginning {args.idle_minutes:g}-minute idle audit.", flush=True)
    idle_started_at, idle_completed_at = audit_idle(
        host, port, args.idle_minutes
    )

    log_path = args.output_dir / "03_ollama_startup.log"
    process, restart_started_at = start_ollama(args.ollama_executable, log_path)
    ready_seconds = wait_for_ready(args.base_url, process, args.startup_timeout)
    ollama_ready_at = utc_timestamp()
    print(
        f"Ollama ready in {ready_seconds:.3f}s; starting first measured request.",
        flush=True,
    )

    prompts = CONTROL.build_frozen_prompts(args.user_input)
    prompt = prompts.resolver if args.endpoint == "resolver" else prompts.main
    think = CONTROL.parse_think(args.main_think)
    client = CONTROL.create_client(args.base_url, args.timeout)
    records: list[dict[str, Any]] = []
    common = {
        "session": args.session,
        "endpoint_kind": args.endpoint,
        "idle_minutes_claimed": args.idle_minutes,
        "cold_start_mode": "ollama_process_absent_and_port_closed",
        "controller_pid": os.getpid(),
        "ollama_pid": process.pid,
        "idle_started_at": idle_started_at,
        "idle_completed_at": idle_completed_at,
        "restart_started_at": restart_started_at,
        "ollama_ready_at": ollama_ready_at,
        "ollama_ready_seconds": ready_seconds,
    }

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
            record.update(common)
            record["position"] = position
            records.append(record)
            suffix = f" ERROR={record['error']}" if record.get("error") else ""
            print(
                f"session={args.session} position={position:02d} "
                f"wall={record.get('wall_clock_seconds')}s{suffix}",
                flush=True,
            )
    finally:
        client.close()

    jsonl_path, csv_path = write_records(records, args.endpoint, args.output_dir)
    print(f"JSONL: {jsonl_path}")
    print(f"CSV:   {csv_path}")
    print(f"Ollama startup log: {log_path}")
    return 1 if any(record.get("error") for record in records) else 0


def parse_args() -> argparse.Namespace:
    default_executable = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Ollama"
        / "ollama.exe"
    )
    parser = argparse.ArgumentParser(
        description="Run a verified local Ollama cold-start latency session."
    )
    parser.add_argument("--endpoint", choices=("resolver", "main"), default="resolver")
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--idle-minutes", type=float, required=True)
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--user-input", default="Hello?")
    parser.add_argument("--model", default=CONTROL.settings.ollama_model)
    parser.add_argument("--base-url", default=CONTROL.settings.ollama_base_url)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--main-think", choices=("config", "true", "false"), default="config")
    parser.add_argument("--ollama-executable", type=Path, default=default_executable)
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    if args.session < 1:
        parser.error("--session must be a positive integer")
    if args.idle_minutes <= 0:
        parser.error("--idle-minutes must be greater than zero")
    if args.requests < 1:
        parser.error("--requests must be at least one")
    if args.timeout <= 0 or args.startup_timeout <= 0:
        parser.error("timeouts must be greater than zero")
    if not args.ollama_executable.is_file():
        parser.error(f"Ollama executable not found: {args.ollama_executable}")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
