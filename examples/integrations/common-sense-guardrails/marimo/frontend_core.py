"""Import-safe fixture request core shared by the Marimo and script surfaces."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from claims_audit import build_claims_reasoning_record  # noqa: E402
from main import build_reasoning_record  # noqa: E402


SCENARIOS = (
    "car-wash",
    "coupon-stack",
    "pallet-door",
    "cold-chain",
    "synthetic-claims-audit",
)
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


@contextmanager
def _selected_provider_environment(
    provider: str | None, model: str | None
) -> Iterator[None]:
    """Temporarily expose submitted provider selection to the canonical runner."""

    original = {
        name: os.environ.get(name) for name in ("NXUSKIT_PROVIDER", "NXUSKIT_MODEL")
    }
    try:
        if provider is not None:
            os.environ["NXUSKIT_PROVIDER"] = provider
        if model is not None:
            os.environ["NXUSKIT_MODEL"] = model
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _enabled(entry_id: str, entries: Sequence[Mapping[str, object]] | None) -> bool:
    if entries is None:
        return False
    return any(
        item.get("id") == entry_id and item.get("enabled") is True for item in entries
    )


def _submitted_request(
    request: Mapping[str, Any],
    *,
    submitted: bool,
    provider_availability: Sequence[Mapping[str, object]] | None,
    mechanism_availability: Sequence[Mapping[str, object]] | None,
) -> dict[str, Any]:
    scenario = str(request.get("scenario", ""))
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    mode = str(request.get("mode", "fixture"))
    if mode not in {"fixture", "auto", "live"}:
        raise ValueError("mode must be fixture, auto, or live")
    provider = request.get("provider")
    model = request.get("model")
    mechanisms = _selected_items(request.get("mechanisms", []))
    max_repair_attempts = int(request.get("max_repair_attempts", 3))
    if not 1 <= max_repair_attempts <= 10:
        raise ValueError("max_repair_attempts must be between 1 and 10")
    if scenario != "synthetic-claims-audit" and not mechanisms:
        raise ValueError("at least one mechanism is required for this scenario")

    if not submitted:
        return {
            "mode": mode,
            "record": None,
            "effective_guardrails": mechanisms,
            "pro_availability": [],
            "requested_provider": str(provider) if provider is not None else None,
            "requested_model": str(model) if model else None,
            "message": "Select inputs, then press Analyze to build the fixture or live record.",
        }

    if mode in {"auto", "live"} and provider is not None:
        if not _enabled(str(provider), provider_availability):
            raise ValueError(f"disabled provider: {provider}")
    if mode == "live" and provider is None:
        raise ValueError("live mode requires a selected enabled provider")
    if mode == "live":
        for mechanism in mechanisms:
            if not _enabled(mechanism, mechanism_availability):
                raise ValueError(f"disabled mechanism: {mechanism}")

    if scenario == "synthetic-claims-audit":
        record = build_claims_reasoning_record()
    else:
        runner_mode = "mock" if mode == "fixture" else mode
        with _selected_provider_environment(
            str(provider) if provider is not None else None,
            str(model) if model is not None else None,
        ):
            record = build_reasoning_record(
                scenario,
                runner_mode,
                None,
                ",".join(mechanisms),
                max_repair_attempts,
            )
    return {
        "mode": mode,
        "record": record,
        "effective_guardrails": mechanisms,
        "pro_availability": [],
        "requested_provider": str(provider) if provider is not None else None,
        "requested_model": str(model) if model else None,
        "message": "Record built after explicit Analyze selection.",
    }


def analyze_request(
    request: Mapping[str, Any] | None = None,
    *,
    submitted: bool | None = None,
    provider_availability: Sequence[Mapping[str, object]] | None = None,
    mechanism_availability: Sequence[Mapping[str, object]] | None = None,
    scenario: str | None = None,
    selected_guardrails: Iterable[str] | str | None = None,
    analyze: bool | None = None,
) -> dict[str, Any]:
    """Build a record only after Analyze, preserving the phase-one fixture API."""

    if request is not None:
        return _submitted_request(
            request,
            submitted=bool(submitted),
            provider_availability=provider_availability,
            mechanism_availability=mechanism_availability,
        )

    if scenario is None or selected_guardrails is None or analyze is None:
        raise TypeError(
            "legacy calls require scenario, selected_guardrails, and analyze"
        )

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
