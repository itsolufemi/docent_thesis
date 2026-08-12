from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_API_URL = "http://127.0.0.1:8000/api/query"

BACKEND_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CASES_FILE = (
    BACKEND_ROOT
    / "tests/prompt_behaviour"
    / "backchannel_handling.json"
)

DEFAULT_OUTPUT_DIRECTORY = (
    BACKEND_ROOT
    / "tmp"
    / "prompt_experiments"
)


def load_suite(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Test suite file was not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        suite = json.load(file)

    cases = suite.get("cases")

    if not isinstance(cases, list) or not cases:
        raise ValueError(
            "The suite must contain a non-empty 'cases' list."
        )

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(
                f"Case {index} must be a JSON object."
            )

        if not case.get("id"):
            raise ValueError(
                f"Case {index} has no 'id'."
            )

        # Support two case shapes:
        # - legacy/simpler: case contains a top-level 'query'
        # - per-turn: case contains a non-empty 'turns' list where each turn has a 'query'
        if not case.get("query"):
            turns = case.get("turns")
            if not isinstance(turns, list) or not turns:
                raise ValueError(
                    f"Case {index} has no 'query' and no non-empty 'turns' list."
                )

            for t_index, turn in enumerate(turns, start=1):
                if not isinstance(turn, dict):
                    raise ValueError(
                        f"Case {index}, turn {t_index} must be a JSON object."
                    )

                if not turn.get("query"):
                    raise ValueError(
                        f"Case {index}, turn {t_index} has no 'query'."
                    )

    return suite


def run_case(
    *,
    api_url: str,
    case: dict[str, Any],
    timeout_seconds: float,
    include_debug: bool,
) -> dict[str, Any]:
    turns = case.get("turns", [])

    if not turns:
        raise ValueError(
            f"Case {case['id']} contains no turns."
        )

    turn_results: list[dict[str, Any]] = []
    conversation_id: str | None = None

    # One client per case means all turns inside this case
    # share the conversation cookie.
    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
    ) as client:
        for turn_number, turn in enumerate(
            turns,
            start=1,
        ):
            payload = {
                "text": turn["query"],
                "subject_reference": turn.get(
                    "subject_reference"
                ),
                "debug": include_debug,
            }

            response = client.post(
                api_url,
                json=payload,
            )

            response.raise_for_status()
            response_data = response.json()

            returned_conversation_id = (
                response_data.get("conversation_id")
            )

            if not returned_conversation_id:
                raise RuntimeError(
                    f"Case {case['id']}, turn "
                    f"{turn_number} returned no "
                    "conversation ID."
                )

            if conversation_id is None:
                conversation_id = (
                    returned_conversation_id
                )
            elif (
                returned_conversation_id
                != conversation_id
            ):
                raise RuntimeError(
                    f"Case {case['id']} changed "
                    "conversation ID between turns."
                )

            turn_results.append(
                {
                    "turn_number": turn_number,
                    "query": turn["query"],
                    "requested_subject_reference": (
                        turn.get("subject_reference")
                    ),
                    "returned_subject_reference": (
                        response_data.get(
                            "subject_reference"
                        )
                    ),
                    "response": response_data.get(
                        "response"
                    ),
                    "sources": response_data.get(
                        "sources",
                        [],
                    ),
                    "debug": response_data.get(
                        "debug"
                    ),
                }
            )

    return {
        "case_id": case["id"],
        "description": case.get("description"),
        "conversation_id": conversation_id,
        "turns": turn_results,
        "status": "completed",
    }


def build_output_path(
    output_directory: Path,
    suite_name: str,
) -> Path:
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    safe_suite_name = "".join(
        character
        if character.isalnum() or character in {"-", "_"}
        else "_"
        for character in suite_name
    )

    return (
        output_directory
        / f"{safe_suite_name}_{timestamp}.json"
    )


def run_suite(
    *,
    suite: dict[str, Any],
    api_url: str,
    timeout_seconds: float,
    include_debug: bool,
) -> dict[str, Any]:
    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    results: list[dict[str, Any]] = []

    for position, case in enumerate(
        suite["cases"],
        start=1,
    ):
        case_id = case["id"]

        # Determine a display query for logs: prefer top-level `query`,
        # otherwise use the first turn's query when present.
        display_query = case.get("query")
        if not display_query:
            turns = case.get("turns", [])
            if turns and isinstance(turns, list):
                first_turn = turns[0]
                display_query = (
                    first_turn.get("query") if isinstance(first_turn, dict) else None
                )

        print(
            f"[{position}/{len(suite['cases'])}] "
            f"Running {case_id}: {display_query}"
        )

        try:
            result = run_case(
                api_url=api_url,
                case=case,
                timeout_seconds=timeout_seconds,
                include_debug=include_debug,
            )

            results.append(result)

            print(
                "  Conversation ID: "
                f"{result['conversation_id']}"
            )

        except Exception as error:
            results.append(
                {
                    "case_id": case_id,
                    "query": case.get("query") or (
                        (case.get("turns") or [])[0].get("query")
                        if case.get("turns")
                        else None
                    ),
                    "requested_subject_reference": (
                        case.get("subject_reference")
                    ),
                    "conversation_id": None,
                    "response": None,
                    "status": "failed",
                    "error": str(error),
                }
            )

            print(
                f"  Failed: {error}",
                file=sys.stderr,
            )

    completed_at = datetime.now(
        timezone.utc
    ).isoformat()

    conversation_ids = [
        result["conversation_id"]
        for result in results
        if result.get("conversation_id")
    ]

    return {
        "suite_name": suite.get(
            "suite_name",
            "unnamed_suite",
        ),
        "description": suite.get("description"),
        "started_at": started_at,
        "completed_at": completed_at,
        "api_url": api_url,
        "each_case_uses_fresh_conversation": True,
        "case_count": len(suite["cases"]),
        "completed_count": sum(
            result["status"] == "completed"
            for result in results
        ),
        "failed_count": sum(
            result["status"] == "failed"
            for result in results
        ),
        "conversation_ids": conversation_ids,
        "results": results,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run qualitative prompt-behaviour cases, "
            "each in a fresh Docent conversation."
        )
    )

    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_FILE,
        help=(
            "Path to the JSON test-suite file."
        ),
    )

    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=(
            "Docent query endpoint. "
            f"Default: {DEFAULT_API_URL}"
        ),
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help=(
            "Timeout in seconds for each query."
        ),
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Request and store the complete debug payload."
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help=(
            "Directory in which the run manifest is saved."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        suite = load_suite(
            arguments.cases.resolve()
        )

        result = run_suite(
            suite=suite,
            api_url=arguments.api_url,
            timeout_seconds=arguments.timeout,
            include_debug=arguments.debug,
        )

        arguments.output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = build_output_path(
            output_directory=(
                arguments.output_directory
            ),
            suite_name=result["suite_name"],
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        print("\nConversation IDs")
        print("================")

        for case_result in result["results"]:
            print(
                f"{case_result['case_id']}: "
                f"{case_result.get('conversation_id')}"
            )

        print(
            f"\nRun manifest saved to:\n{output_path}"
        )

        return (
            0
            if result["failed_count"] == 0
            else 1
        )

    except Exception as error:
        print(
            f"Suite failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())