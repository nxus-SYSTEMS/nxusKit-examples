"""Import-safe fixture request core shared by the Marimo and script surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from claims_audit import build_claims_reasoning_record  # noqa: E402
from main import build_reasoning_record  # noqa: E402


SCENARIOS = ("cold-chain", "synthetic-claims-audit")
COMMUNITY_GUARDRAILS = ("clips", "bn")
PRO_GUARDRAILS = ("solver", "zen")
CLAIMS_GUARDRAIL = "claims-audit"
DEFAULT_GUARDRAILS = ("clips", "bn")


def _selected_items(selected_guardrails: Iterable[str] | str) -> list[str]:
    if isinstance(selected_guardrails, str):
        selected = selected_guardrails.split(",")
    else:
        selected = list(selected_guardrails)
    return [item.strip().lower() for item in selected if item and item.strip()]


def _pro_availability(selected: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": item,
            "tier": "pro",
            "selected": True,
            "available": False,
            "reason": "The fixture frontend does not invoke Pro mechanisms.",
        }
        for item in selected
        if item in PRO_GUARDRAILS
    ]


def _effective_guardrails(scenario: str, selected: list[str]) -> list[str]:
    if scenario == "synthetic-claims-audit":
        return [CLAIMS_GUARDRAIL]
    effective = [item for item in selected if item in COMMUNITY_GUARDRAILS]
    return effective or ["clips"]


def analyze_request(
    *, scenario: str, selected_guardrails: Iterable[str] | str, analyze: bool
) -> dict[str, Any]:
    """Build one fixture record after an explicit user action only."""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    selected = _selected_items(selected_guardrails)
    availability = _pro_availability(selected)
    effective = _effective_guardrails(scenario, selected)
    if not analyze:
        return {
            "mode": "fixture",
            "record": None,
            "effective_guardrails": effective,
            "pro_availability": availability,
            "message": "Select inputs, then press Analyze to build the fixture record.",
        }

    if scenario == "synthetic-claims-audit":
        record = build_claims_reasoning_record()
    else:
        record = build_reasoning_record(scenario, "mock", "ce", ",".join(effective))
    return {
        "mode": "fixture",
        "record": record,
        "effective_guardrails": effective,
        "pro_availability": availability,
        "message": "Fixture record built after explicit Analyze selection.",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fixture-first Marimo reasoning-record frontend script."
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="cold-chain")
    parser.add_argument(
        "--guardrails",
        default=",".join(DEFAULT_GUARDRAILS),
        help="Comma-separated Community or explicitly selected Pro mechanisms.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Explicitly build one offline fixture record.",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured output.")
    return parser.parse_args(argv)


def run_script(argv: list[str]) -> int:
    args = parse_args(argv)
    response = analyze_request(
        scenario=args.scenario,
        selected_guardrails=args.guardrails,
        analyze=args.analyze,
    )
    if args.json:
        print(json.dumps(response, indent=2, sort_keys=True))
    else:
        print(response["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(run_script(sys.argv[1:]))
