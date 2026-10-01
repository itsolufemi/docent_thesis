from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
for path in (BACKEND_ROOT, REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from docent.services.docent_discovery_service import (  # noqa: E402
    discover_docent_candidates,
)


CALIBRATION_CASES = [
    {
        "name": "orientalism",
        "query": (
            "nineteenth-century Orientalism and European representations "
            "of North Africa"
        ),
        "expected_titles": ["the arab tent"],
    },
    {
        "name": "rococo mythology",
        "query": "Rococo mythology, sensuality, and playful courtly fantasy",
        "expected_titles": ["the rising of the sun", "the rape of europa"],
    },
    {
        "name": "literary drama",
        "query": "supernatural literary drama, temptation, and moral conflict",
        "expected_titles": ["faust and mephistopheles"],
    },
    {
        "name": "royal portraiture",
        "query": "monarchy, royal identity, and nineteenth-century portraiture",
        "expected_titles": ["queen victoria"],
    },
    {
        "name": "painterly portrait technique",
        "query": "expressive brushwork and painterly handling in society portraiture",
        "expected_titles": [
            "margaret, countess of blessington",
            "portrait of a lady",
        ],
    },
    {
        "name": "maternal portraiture",
        "query": "maternal affection, childhood, and family portraiture",
        "expected_titles": ["mrs susanna hoare and child"],
    },
]


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def run_calibration() -> dict:
    cases: list[dict] = []

    for case in CALIBRATION_CASES:
        result = discover_docent_candidates(
            query=case["query"],
            scope="collection",
            current_reference=None,
        )
        telemetry = result["telemetry"]
        expected = {
            _normalise(title)
            for title in case["expected_titles"]
        }
        expected_matches = [
            candidate
            for candidate in telemetry["raw_candidates"]
            if _normalise(candidate["title"]) in expected
        ]
        best_match = min(
            expected_matches,
            key=lambda candidate: candidate["rank"],
            default=None,
        )
        cases.append(
            {
                "name": case["name"],
                "query": case["query"],
                "threshold": telemetry["threshold"],
                "expected_titles": case["expected_titles"],
                "best_expected_rank": (
                    best_match["rank"] if best_match else None
                ),
                "best_expected_score": (
                    best_match["semantic_score"] if best_match else None
                ),
                "best_expected_passed_threshold": (
                    best_match["passed_threshold"] if best_match else False
                ),
                "raw_candidates": telemetry["raw_candidates"],
            }
        )

    return {
        "threshold": (
            cases[0]["threshold"]
            if cases
            else None
        ),
        "case_count": len(cases),
        "cases": cases,
    }


def print_report(report: dict) -> None:
    print(
        "case | expected rank | expected score | passes gate | top candidate"
    )
    print("-" * 92)
    for case in report["cases"]:
        top = (
            case["raw_candidates"][0]
            if case["raw_candidates"]
            else None
        )
        top_summary = (
            f"{top['title']} ({top['semantic_score']:.4f})"
            if top
            else "none"
        )
        print(
            f"{case['name']} | "
            f"{case['best_expected_rank']} | "
            f"{case['best_expected_score']} | "
            f"{case['best_expected_passed_threshold']} | "
            f"{top_summary}"
        )
        for candidate in case["raw_candidates"][:5]:
            marker = (
                "selected"
                if candidate["selected_rank"]
                else (
                    "passed gate"
                    if candidate["passed_threshold"]
                    else "gated"
                )
            )
            print(
                f"  {candidate['rank']}. {candidate['title']} | "
                f"{candidate['semantic_score']:.4f} | {marker}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure pre-gate semantic discovery rankings."
    )
    parser.add_argument("--json-output", type=Path)
    arguments = parser.parse_args()
    report = run_calibration()
    print_report(report)

    if arguments.json_output is not None:
        arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
