"""Import-safe UI contract and safe report projection for the Model Research app."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from availability import inspect_engine_availability, inspect_provider_availability
from config_catalog import build_config_catalog


ROOT = Path(__file__).resolve().parents[1]
MODES = ["mock", "auto", "live", "dry-run-policy", "import-promptfoo"]
INSPECTION_SECTIONS = [
    "Summary",
    "Visual Evidence",
    "Results",
    "Confidence",
    "Capability Truth",
    "Policy",
    "Raw JSON",
]
RELEASED_PRO_FEATURES = ("solver", "zen")


def _project_license_status(
    license_status: Mapping[str, object] | None,
) -> dict[str, object]:
    """Pass only fixed-shape, validated released-feature state to engine checks."""

    status = license_status or {}
    validated = status.get("validated") is True
    granted = status.get("features")
    return {
        "token_detected": bool(status.get("token_detected")),
        "validated": validated,
        "features": [
            feature
            for feature in RELEASED_PRO_FEATURES
            if validated and isinstance(granted, list) and feature in granted
        ],
    }


def workbench_controls(
    *,
    environ: Mapping[str, str] | None = None,
    license_status: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the UI contract without probing runtimes or providers."""

    environment = os.environ if environ is None else environ
    configs = {entry["id"]: entry for entry in build_config_catalog(ROOT)}
    providers = {
        entry["id"]: entry for entry in inspect_provider_availability(environment)
    }
    engines = {
        entry["id"]: entry
        for entry in inspect_engine_availability(
            license_status=_project_license_status(license_status)
        )
    }
    return {
        "configs": configs,
        "providers": providers,
        "engines": engines,
        "modes": MODES,
        "form_fields": [
            "config_id",
            "mode",
            "provider",
            "model",
            "include_tests",
            "exclude_tests",
            "allow_external",
            "write_reports",
        ],
        "primary_action": {"id": "run-evaluation", "label": "Run evaluation"},
        "inspection_sections": INSPECTION_SECTIONS,
    }


def normalise_filters(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def availability_markdown(controls: Mapping[str, object]) -> str:
    """Render visible, value-free availability reasons beside disabled controls."""

    configs = controls["configs"]
    providers = controls["providers"]
    engines = controls["engines"]
    assert isinstance(configs, Mapping)
    assert isinstance(providers, Mapping)
    assert isinstance(engines, Mapping)
    lines = ["## Availability and execution truth"]
    for title, entries in (
        ("Unavailable configs", configs),
        ("Providers", providers),
        ("Engines", engines),
    ):
        lines.append(f"### {title}")
        for entry_id, entry in entries.items():
            if not isinstance(entry, Mapping):
                continue
            if title == "Unavailable configs" and entry.get("enabled") is True:
                continue
            lines.append(
                f"- `{entry_id}` — {entry.get('tier', 'community')} / "
                f"{entry.get('status', 'unavailable')}: {entry.get('reason', '')}"
            )
    return "\n".join(lines)


def safe_report_json(report: Mapping[str, Any]) -> dict[str, object]:
    """Expose canonical evidence fields while excluding raw output and prompt content."""

    safe_results = []
    for item in report.get("results", []):
        if not isinstance(item, Mapping):
            continue
        safe_results.append(
            {
                key: value
                for key, value in item.items()
                if key not in {"output", "prompt", "messages", "raw_response"}
            }
        )
    return {
        "config_id": report.get("config_id"),
        "final_status": report.get("final_status"),
        "results": safe_results,
        "bayesian_confidence": report.get("bayesian_confidence"),
        "policy_recommendations": report.get("policy_recommendations"),
        "capability_truth_table": report.get("capability_truth_table"),
    }
