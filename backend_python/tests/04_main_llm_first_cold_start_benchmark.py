"""Test whether Ollama's first-cloud-request penalty also affects /api/chat.

Experiment 04 reuses Experiment 03's verified shutdown audit, local Ollama
restart, readiness probe, and measurement implementation. The endpoint is
deliberately fixed to ``main``: each session's first cloud model request is a
streaming ``/api/chat`` call using the frozen main-LLM prompt. No resolver
``/api/generate`` request is made before or during the session.

Example::

    ..\\venv\\Scripts\\python.exe 04_main_llm_first_cold_start_benchmark.py \\
        --session 1 --idle-minutes 5
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
COLD_START_PATH = HERE / "03_full_system_cold_start_benchmark.py"


def load_cold_start_module():
    spec = importlib.util.spec_from_file_location(
        "verified_ollama_cold_start_benchmark",
        COLD_START_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Experiment 03: {COLD_START_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COLD = load_cold_start_module()


def experiment_04_output_stem(endpoint_kind: str, output_dir: Path) -> Path:
    if endpoint_kind != "main":
        raise RuntimeError("Experiment 04 permits only the main /api/chat endpoint")
    return output_dir / "04_main_llm_first_cold_start_results"


# Experiment 03 deliberately centralizes the safety-critical process shutdown,
# port audit, restart, and request measurement. Only the result namespace and
# fixed endpoint differ here.
COLD.output_stem = experiment_04_output_stem


def parse_args() -> argparse.Namespace:
    default_executable = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Ollama"
        / "ollama.exe"
    )
    parser = argparse.ArgumentParser(
        description=(
            "Run a verified Ollama cold start with /api/chat as the first "
            "cloud request."
        )
    )
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--idle-minutes", type=float, default=5.0)
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--user-input", default="Hello?")
    parser.add_argument("--model", default=COLD.CONTROL.settings.ollama_model)
    parser.add_argument("--base-url", default=COLD.CONTROL.settings.ollama_base_url)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument(
        "--main-think",
        choices=("config", "true", "false"),
        default="config",
    )
    parser.add_argument(
        "--ollama-executable",
        type=Path,
        default=default_executable,
    )
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()
    args.endpoint = "main"

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
    raise SystemExit(COLD.run(parse_args()))
