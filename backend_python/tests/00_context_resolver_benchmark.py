"""Benchmark Docent's two Ollama request paths with frozen inputs.

The benchmark deliberately bypasses the browser, ASR, retrieval, TTS, cookies,
and conversation persistence. It sends the same resolver and main-LLM prompts
on every iteration and records both client-observed and provider-reported
timings.

Run from anywhere with the backend virtual environment, for example:

    backend_python\\venv\\Scripts\\python.exe \
        backend_python\\tests\\00_context_resolver_benchmark.py

No requests are made when ``--dry-run`` is supplied.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import httpx


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend_python"

for import_root in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from config import settings  # noqa: E402
from conversation_core.schemas.conversation_schemas import (  # noqa: E402
    DialogueTurn,
)
from conversation_core.services.prompt_service import (  # noqa: E402
    format_dialogue_history_for_prompt,
)
from docent.services.docent_prompt_service import docent_build_prompt  # noqa: E402
from docent.services.docent_query_service import (  # noqa: E402
    CONTEXT_RESOLUTION_INSTRUCTIONS,
)


PROVIDER_DURATION_FIELDS = (
    "total_duration",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
)

CSV_FIELDS = (
    "phase",
    "client_mode",
    "run",
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
)


@dataclass(frozen=True)
class FrozenPrompts:
    user_input: str
    resolver: str
    main: str


class ResultWriter:
    """Append each completed request immediately to JSONL and CSV."""

    def __init__(self, output_stem: Path) -> None:
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = output_stem.with_suffix(".jsonl")
        self.csv_path = output_stem.with_suffix(".csv")
        self._jsonl_file = self.jsonl_path.open("w", encoding="utf-8")
        self._csv_file = self.csv_path.open(
            "w",
            encoding="utf-8",
            newline="",
        )
        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
        )
        self._csv_writer.writeheader()

    def write(self, record: dict[str, Any]) -> None:
        self._jsonl_file.write(
            json.dumps(record, ensure_ascii=False, default=str) + "\n"
        )
        self._jsonl_file.flush()
        self._csv_writer.writerow(record)
        self._csv_file.flush()

    def close(self) -> None:
        self._jsonl_file.close()
        self._csv_file.close()

    def __enter__(self) -> ResultWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def build_frozen_prompts(user_input: str) -> FrozenPrompts:
    """Build the same empty-history prompts used by Docent production code."""
    formatted_history = format_dialogue_history_for_prompt(
        dialogue_history=[],
        user_label="Visitor",
        assistant_label="Docent",
    )

    resolver_prompt = f"""
{CONTEXT_RESOLUTION_INSTRUCTIONS}

RECENT DIALOGUE
{formatted_history}

CURRENT UTTERANCE
{user_input}

JSON:
""".strip()

    main_prompt = docent_build_prompt(
        user_input=user_input,
        dialogue_history=[
            DialogueTurn(user=user_input)
        ],
        artwork=None,
        retrieved_documents=[],
        retrieved_chunks=[],
    )

    return FrozenPrompts(
        user_input=user_input,
        resolver=resolver_prompt,
        main=main_prompt,
    )


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def duration_seconds(value: Any) -> float | None:
    """Convert Ollama's nanosecond duration values to seconds."""
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) / 1_000_000_000, 9)


def add_provider_durations(
    record: dict[str, Any],
    response_data: dict[str, Any],
) -> None:
    for field in PROVIDER_DURATION_FIELDS:
        value = response_data.get(field)
        record[f"provider_{field}"] = value
        record[f"provider_{field}_seconds"] = duration_seconds(value)


def base_record(
    *,
    phase: str,
    client_mode: str,
    run: int,
    model: str,
    endpoint: str,
    prompt: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "client_mode": client_mode,
        "run": run,
        "timestamp": utc_timestamp(),
        "model": model,
        "endpoint": endpoint,
        "prompt_chars": len(prompt),
        "prompt_sha256": prompt_sha256(prompt),
        "wall_clock_seconds": None,
        "request_to_response_headers_seconds": None,
        "request_to_first_chunk_seconds": None,
        "request_to_first_content_token_seconds": None,
        "full_generation_seconds": None,
        "result": "",
        "error": None,
    }


def run_resolver_request(
    client: httpx.Client,
    *,
    phase: str,
    client_mode: str,
    run: int,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    record = base_record(
        phase=phase,
        client_mode=client_mode,
        run=run,
        model=model,
        endpoint="/api/generate",
        prompt=prompt,
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
        "think": False,
    }

    started_at = perf_counter()
    try:
        response = client.post(
            "/api/generate",
            json=payload,
        )
        record["request_to_response_headers_seconds"] = round(
            perf_counter() - started_at,
            6,
        )
        response.raise_for_status()
        response_data = response.json()
        record["raw_response"] = response_data
        record["result"] = str(response_data.get("response", "")).strip()
        add_provider_durations(record, response_data)
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
    finally:
        elapsed = round(perf_counter() - started_at, 6)
        record["wall_clock_seconds"] = elapsed
        record["full_generation_seconds"] = elapsed

    return record


def run_main_request(
    client: httpx.Client,
    *,
    phase: str,
    client_mode: str,
    run: int,
    model: str,
    prompt: str,
    think: bool | None,
) -> dict[str, Any]:
    record = base_record(
        phase=phase,
        client_mode=client_mode,
        run=run,
        model=model,
        endpoint="/api/chat",
        prompt=prompt,
    )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    if think is not None:
        payload["think"] = think

    started_at = perf_counter()
    raw_chunks: list[dict[str, Any]] = []
    response_parts: list[str] = []

    try:
        with client.stream(
            method="POST",
            url="/api/chat",
            json=payload,
        ) as response:
            record["request_to_response_headers_seconds"] = round(
                perf_counter() - started_at,
                6,
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(chunk, dict):
                    continue

                raw_chunks.append(chunk)
                elapsed = round(perf_counter() - started_at, 6)

                if record["request_to_first_chunk_seconds"] is None:
                    record["request_to_first_chunk_seconds"] = elapsed

                message = chunk.get("message") or {}
                content = message.get("content") or ""
                if content:
                    if record["request_to_first_content_token_seconds"] is None:
                        record["request_to_first_content_token_seconds"] = elapsed
                    response_parts.append(str(content))

        record["raw_response"] = raw_chunks
        record["result"] = "".join(response_parts).strip()

        for chunk in reversed(raw_chunks):
            if any(field in chunk for field in PROVIDER_DURATION_FIELDS):
                add_provider_durations(record, chunk)
                break
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        record["raw_response"] = raw_chunks
        record["result"] = "".join(response_parts).strip()
    finally:
        elapsed = round(perf_counter() - started_at, 6)
        record["wall_clock_seconds"] = elapsed
        record["full_generation_seconds"] = elapsed

    return record


def create_client(base_url: str, timeout: float) -> httpx.Client:
    """Match the production client's pooling and keep-alive configuration."""
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(
            timeout=timeout,
            connect=min(15.0, timeout),
        ),
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=60.0,
        ),
    )


def execute_request(
    *,
    endpoint: str,
    persistent_client: httpx.Client | None,
    base_url: str,
    timeout: float,
    phase: str,
    client_mode: str,
    run: int,
    model: str,
    prompts: FrozenPrompts,
    think: bool | None,
) -> dict[str, Any]:
    owns_client = persistent_client is None
    client = persistent_client or create_client(base_url, timeout)

    try:
        if endpoint == "resolver":
            return run_resolver_request(
                client,
                phase=phase,
                client_mode=client_mode,
                run=run,
                model=model,
                prompt=prompts.resolver,
            )

        return run_main_request(
            client,
            phase=phase,
            client_mode=client_mode,
            run=run,
            model=model,
            prompt=prompts.main,
            think=think,
        )
    finally:
        if owns_client:
            client.close()


def display_record(record: dict[str, Any]) -> None:
    endpoint = record["endpoint"]
    phase = record["phase"]
    run = record["run"]
    wall = record["wall_clock_seconds"]
    first_content = record["request_to_first_content_token_seconds"]
    error = record["error"]

    detail = f"wall={wall:.3f}s" if isinstance(wall, float) else "wall=n/a"
    if isinstance(first_content, float):
        detail += f" ttft={first_content:.3f}s"
    if error:
        detail += f" ERROR={error}"

    print(f"[{record['client_mode']}] {phase} {run:02d} {endpoint}: {detail}")


def run_series(
    *,
    writer: ResultWriter,
    client_mode: str,
    warmups: int,
    runs: int,
    base_url: str,
    timeout: float,
    model: str,
    prompts: FrozenPrompts,
    think: bool | None,
) -> int:
    persistent_client = (
        create_client(base_url, timeout)
        if client_mode == "persistent"
        else None
    )
    failures = 0

    try:
        phases: Iterable[tuple[str, int]] = (
            ("warmup", warmups),
            ("measured", runs),
        )

        for phase, count in phases:
            for run in range(1, count + 1):
                # Alternation is deliberate: correlated spikes implicate shared
                # provider/runtime conditions rather than a single request path.
                for endpoint in ("resolver", "main"):
                    record = execute_request(
                        endpoint=endpoint,
                        persistent_client=persistent_client,
                        base_url=base_url,
                        timeout=timeout,
                        phase=phase,
                        client_mode=client_mode,
                        run=run,
                        model=model,
                        prompts=prompts,
                        think=think,
                    )
                    writer.write(record)
                    display_record(record)
                    failures += int(record["error"] is not None)
    finally:
        if persistent_client is not None:
            persistent_client.close()

    return failures


def parse_think(value: str) -> bool | None:
    if value == "config":
        return settings.ollama_main_think
    return value == "true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark identical context-resolver and main-LLM requests, "
            "alternating the two production Ollama paths."
        )
    )
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--user-input", default="Hello?")
    parser.add_argument("--model", default=settings.ollama_model)
    parser.add_argument("--base-url", default=settings.ollama_base_url)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--client-mode",
        choices=("persistent", "fresh", "both"),
        default="persistent",
        help=(
            "Reuse one production-like HTTP client, create a client per request, "
            "or run both experiments."
        ),
    )
    parser.add_argument(
        "--main-think",
        choices=("config", "true", "false"),
        default="config",
        help="Use OLLAMA_MAIN_THINK by default, or override it explicitly.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and report the frozen prompts without making HTTP requests.",
    )
    parser.add_argument(
        "--print-prompts",
        action="store_true",
        help="Print the complete frozen prompts (useful with --dry-run).",
    )
    args = parser.parse_args()

    if args.warmups < 0 or args.runs < 1:
        parser.error("--warmups must be >= 0 and --runs must be >= 1")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")

    return args


def main() -> int:
    args = parse_args()
    prompts = build_frozen_prompts(args.user_input)
    think = parse_think(args.main_think)

    print(f"Model: {args.model}")
    print(f"Base URL: {args.base_url.rstrip('/')}")
    print(
        "Resolver prompt: "
        f"{len(prompts.resolver)} chars, {prompt_sha256(prompts.resolver)}"
    )
    print(
        "Main prompt: "
        f"{len(prompts.main)} chars, {prompt_sha256(prompts.main)}"
    )
    print(f"Main think: {think!r}")

    if args.print_prompts:
        print("\n--- resolver prompt ---\n")
        print(prompts.resolver)
        print("\n--- main prompt ---\n")
        print(prompts.main)

    if args.dry_run:
        print("Dry run complete; no HTTP requests were made.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_stem = (
        args.output_dir
        / f"00_context_resolver_benchmark_results_{timestamp}"
    )
    metadata_path = output_stem.with_name(output_stem.name + "_metadata.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "created_at": utc_timestamp(),
                "model": args.model,
                "base_url": args.base_url.rstrip("/"),
                "warmups": args.warmups,
                "runs": args.runs,
                "client_mode": args.client_mode,
                "main_think": think,
                "user_input": prompts.user_input,
                "resolver_prompt": prompts.resolver,
                "main_prompt": prompts.main,
                "provider_duration_unit": "nanoseconds",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    modes = (
        ("persistent", "fresh")
        if args.client_mode == "both"
        else (args.client_mode,)
    )
    failures = 0

    with ResultWriter(output_stem) as writer:
        for client_mode in modes:
            failures += run_series(
                writer=writer,
                client_mode=client_mode,
                warmups=args.warmups,
                runs=args.runs,
                base_url=args.base_url,
                timeout=args.timeout,
                model=args.model,
                prompts=prompts,
                think=think,
            )

        print(f"JSONL: {writer.jsonl_path}")
        print(f"CSV:   {writer.csv_path}")
    print(f"Metadata: {metadata_path}")

    if failures:
        print(f"Completed with {failures} failed request(s).", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
