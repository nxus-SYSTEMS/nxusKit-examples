#!/usr/bin/env python3
"""Fixture runner that mimics DevOps operational report shapes.

This is intentionally tiny and deterministic. It lets the model research
harness test external-command adapters without depending on Ollama, DevOps
checkout paths, or private fixture data.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def common_sense() -> dict:
    return {
        "config": {"fixture": "car-wash", "models": ["fixture-small-model"]},
        "results": [
            {
                "model": "fixture-small-model",
                "target_candidate": True,
                "simple": {"action": "walk", "error": None},
                "constrained": {"action": "walk", "error": None},
                "enhanced": {"action": "drive", "error": None},
            }
        ],
    }


def tool_intent() -> dict:
    return {
        "config": {"scenario": "nxuskit-carwash-tool-intent"},
        "results": [
            {
                "model": "fixture-tool-model",
                "status": "PASS",
                "pass_smoke": True,
                "parseable_json": True,
                "recognized_tool": True,
                "recognized_provider": True,
            }
        ],
    }


def safe_labs() -> dict:
    return {
        "generated_at": "fixture",
        "results": [
            {
                "row": {
                    "model": "fixture-vlm",
                    "document_id": "hba1c_20250812",
                    "status": "PASS",
                    "expected_count": 6,
                    "value_correct_count": 6,
                    "missing_count": 0,
                    "extra_count": 0,
                    "value_accuracy": 1.0,
                    "row_accuracy": 1.0,
                },
                "row_score": {"value_accuracy": 1.0, "row_accuracy": 1.0},
            }
        ],
    }


def pipeline() -> dict:
    return {
        "result": {
            "score": 100.0,
            "found": ["a", "b", "c", "d", "e", "f"],
            "missing": [],
            "extra_rows": 0,
        }
    }


def vision() -> list[dict]:
    return [
        {
            "model": "fixture-vlm",
            "results": {
                "json": {
                    "deterministic": {
                        "status": "PASS",
                        "score": 100.0,
                        "found": ["a", "b", "c", "d", "e", "f"],
                        "missing": [],
                        "extra_rows": 0,
                    }
                }
            },
        }
    ]


STRATEGIES = {
    "devops-common-sense": common_sense,
    "devops-tool-intent": tool_intent,
    "devops-safe-labs": safe_labs,
    "devops-pipeline": pipeline,
    "devops-vision": vision,
}


def write_capabilities_fixture(output_dir: Path) -> None:
    with (output_dir / "capabilities.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "DateTime",
                "Model",
                "Text",
                "Single",
                "Multi",
                "Tools",
                "JSONInput",
                "JSONOutput",
                "ImageToJSON",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "DateTime": "fixture",
                "Model": "fixture-json-model",
                "Text": "⏭️",
                "Single": "⏭️",
                "Multi": "⏭️",
                "Tools": "⏭️",
                "JSONInput": "0",
                "JSONOutput": "3",
                "ImageToJSON": "0",
            }
        )
    (output_dir / "capabilities.md").write_text("# Fixture Capabilities\n\nPASS\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy",
        required=True,
        choices=sorted([*STRATEGIES, "devops-capabilities"]),
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.strategy == "devops-capabilities":
        write_capabilities_fixture(output_dir)
    else:
        data = STRATEGIES[args.strategy]()
        (output_dir / "detailed_results.json").write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        (output_dir / "summary.md").write_text(f"# Fixture {args.strategy}\n\nPASS\n")
    print(f"wrote fixture report: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
