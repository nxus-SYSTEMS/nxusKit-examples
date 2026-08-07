"""Fail-closed, import-safe availability for the Common Sense Workbench."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from model_discovery import DiscoverySnapshot


CloudProvider = tuple[str, str]

CLOUD_PROVIDERS: tuple[CloudProvider, ...] = (
    ("claude", "ANTHROPIC_API_KEY"),
    ("openai", "OPENAI_API_KEY"),
    ("groq", "GROQ_API_KEY"),
    ("xai", "XAI_API_KEY"),
)
LOCAL_PROVIDERS = ("ollama", "lmstudio")
SCENARIOS = (
    "car-wash",
    "coupon-stack",
    "pallet-door",
    "cold-chain",
    "synthetic-claims-audit",
)
RELEASED_PRO_FEATURES = ("solver", "zen")
REASONING_ENGINES = ("clips", "bn", "solver", "zen", "claims-audit")
ENGINE_SCENARIOS = {
    "clips": {"car-wash", "coupon-stack", "pallet-door", "cold-chain"},
    "bn": {"coupon-stack", "cold-chain"},
    "solver": {"car-wash", "pallet-door"},
    "zen": {"coupon-stack", "cold-chain"},
    "claims-audit": {"synthetic-claims-audit"},
}
ENGINE_LABELS = {
    "clips": "CLIPS",
    "bn": "Bayesian Network",
    "solver": "Solver",
    "zen": "ZEN",
    "claims-audit": "Claims Audit",
}
COUPON_COMPATIBILITY_PATH = (
    Path(__file__).resolve().parents[1]
    / "scenarios"
    / "coupon-stack"
    / "mode-compatibility-v1.0.5.json"
)
GENERIC_MODES = (
    ("fixture", "Fixture"),
    ("auto", "Auto"),
    ("live", "Live"),
)


def coupon_mode_compatibility() -> dict[str, object]:
    """Load the public, non-secret v1.0.5 coupon compatibility policy."""

    payload = json.loads(COUPON_COMPATIBILITY_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("scenario") != "coupon-stack"
        or payload.get("sdk_release") != "1.0.5"
        or not isinstance(payload.get("modes"), dict)
    ):
        raise ValueError("invalid coupon mode compatibility policy")
    return payload


def scenario_mode_options(scenario_id: str) -> list[dict[str, object]]:
    """Project scenario-specific mode state without evaluating any provider."""

    if scenario_id not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    if scenario_id == "coupon-stack":
        compatibility = coupon_mode_compatibility()
        modes = compatibility["modes"]
        assert isinstance(modes, dict)
        code = str(compatibility["compatibility_code"])
        return [
            {
                "id": mode_id,
                "label": label,
                "enabled": bool(modes[mode_id]["enabled"]),
                "resolved_mode": modes[mode_id]["resolved_source"],
                "message": str(modes[mode_id]["message"]),
                "compatibility_code": code,
            }
            for mode_id, label in GENERIC_MODES
        ]
    if scenario_id == "synthetic-claims-audit":
        reason = (
            "This deterministic synthetic data-quality audit is Fixture-only "
            "and does not invoke an LLM provider."
        )
        return [
            {
                "id": mode_id,
                "label": label,
                "enabled": mode_id == "fixture",
                "resolved_mode": "fixture" if mode_id == "fixture" else None,
                "message": reason,
            }
            for mode_id, label in GENERIC_MODES
        ]
    return [
        {
            "id": mode_id,
            "label": label,
            "enabled": True,
            "resolved_mode": mode_id,
            "message": "",
        }
        for mode_id, label in GENERIC_MODES
    ]


def provider_options_for_scenario(
    scenario_id: str,
    providers: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Add scenario applicability while preserving global provider truth."""

    if scenario_id not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    coupon_inapplicable = scenario_id == "coupon-stack"
    applicability_reason = (
        "This provider remains available for supported scenarios, but Coupon "
        "stack cannot use provider Live with nxusKit v1.0.5 because the Python "
        "provider path cannot preserve the required strict schema."
    )
    projected: list[dict[str, object]] = []
    for provider in providers:
        item = dict(provider)
        item.update(
            {
                "applicable": not coupon_inapplicable,
                "applicability_status": (
                    "strict_schema_unavailable_for_scenario"
                    if coupon_inapplicable
                    else "applicable"
                ),
                "applicability_reason": (
                    applicability_reason if coupon_inapplicable else ""
                ),
                "selectable": provider.get("enabled") is True
                and not coupon_inapplicable,
            }
        )
        projected.append(item)
    return projected


def _empty_license_status() -> dict[str, object]:
    return {"token_detected": False, "validated": False, "features": []}


def released_license_status(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Read the released CLI's status and project only validated feature names.

    The runner is injected by tests.  No opaque license fields, token value, or
    provider/runtime operation crosses this availability boundary.
    """

    environment = os.environ if environ is None else environ
    command = [
        environment.get("NXUSKIT_CLI", "nxuskit-cli"),
        "license",
        "status",
        "--json",
    ]
    try:
        result = runner(
            command, text=True, capture_output=True, check=False, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return _empty_license_status()
    if result.returncode != 0:
        return _empty_license_status()
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return _empty_license_status()
    license_info = payload.get("license") if isinstance(payload, Mapping) else None
    if not isinstance(license_info, Mapping):
        return _empty_license_status()

    token_detected = bool(license_info)
    validated = (
        license_info.get("effective_edition") == "pro"
        and license_info.get("status") == "valid"
    )
    if not validated:
        return {
            "token_detected": token_detected,
            "validated": False,
            "features": [],
        }
    granted = license_info.get("features")
    cli_info = payload.get("cli") if isinstance(payload, Mapping) else None
    pro_engines_compiled = (
        isinstance(cli_info, Mapping) and cli_info.get("pro_engines_compiled") is True
    )
    features = [
        feature
        for feature in RELEASED_PRO_FEATURES
        if pro_engines_compiled and isinstance(granted, list) and feature in granted
    ]
    return {
        "token_detected": token_detected,
        "validated": True,
        "features": features,
    }


def _entry(
    entry_id: str,
    *,
    kind: str,
    tier: str,
    enabled: bool,
    status: str,
    reason: str,
) -> dict[str, object]:
    """Return the only safe availability shape shared by both workbenches."""

    return {
        "id": entry_id,
        "kind": kind,
        "tier": tier,
        "visible": True,
        "enabled": enabled,
        "status": status,
        "reason": reason,
        "runtime_executed": False,
    }


def inspect_provider_availability(
    environ: Mapping[str, str],
    discovery_snapshots: Mapping[str, DiscoverySnapshot] | None = None,
) -> list[dict[str, object]]:
    """Project credential-name and safe discovery state without exposing values."""

    snapshots = discovery_snapshots or {}
    entries: list[dict[str, object]] = []
    for provider_id, credential_name in CLOUD_PROVIDERS:
        detected = credential_name in environ
        snapshot = snapshots.get(provider_id)
        state = getattr(snapshot, "state", "idle")
        has_models = bool(getattr(snapshot, "models", ()))
        if not detected:
            enabled = False
            status = "credential_not_detected"
            reason = f"{credential_name} was not detected."
        elif (state == "ready" or state == "stale") and has_models:
            enabled = True
            status = "available"
            reason = (
                "A cached SDK model catalog is available; Refresh models may update it."
                if state == "stale"
                else "SDK-reported models are available after explicit Analyze."
            )
        elif state in {"empty", "stale", "failed"}:
            enabled = False
            status = "runtime_unavailable"
            reason = "Released nxusKit did not report an available model catalog."
        else:
            enabled = True
            status = "available"
            reason = (
                "Credential name detected; SDK model discovery is pending and any "
                "provider call still requires explicit Analyze."
            )
        entries.append(
            _entry(
                provider_id,
                kind="provider",
                tier="community",
                enabled=enabled,
                status=status,
                reason=reason,
            )
        )

    for provider_id in LOCAL_PROVIDERS:
        snapshot = snapshots.get(provider_id)
        state = getattr(snapshot, "state", "idle")
        has_models = bool(getattr(snapshot, "models", ()))
        if (state == "ready" or state == "stale") and has_models:
            enabled = True
            status = "available"
            reason = (
                "A cached local model catalog is available; Refresh models may update it."
                if state == "stale"
                else "Released nxusKit reported available local models."
            )
        elif state == "failed":
            enabled = False
            status = "endpoint_unreachable"
            reason = "Released nxusKit could not reach the local provider."
        elif state in {"empty", "stale"}:
            enabled = False
            status = "runtime_unavailable"
            reason = "Released nxusKit did not report an available local model."
        else:
            enabled = False
            status = "runtime_unavailable"
            reason = "Checking local models through released nxusKit."
        entries.append(
            _entry(
                provider_id,
                kind="provider",
                tier="community",
                enabled=enabled,
                status=status,
                reason=reason,
            )
        )
    return entries


def _pro_entry(
    mechanism: str,
    license_status: Mapping[str, object] | None,
) -> dict[str, object]:
    status = license_status or {}
    if not bool(status.get("token_detected")):
        return _entry(
            mechanism,
            kind="mechanism",
            tier="pro",
            enabled=False,
            status="license_not_detected",
            reason="No validated released nxusKit license status is available.",
        )
    if not bool(status.get("validated")):
        return _entry(
            mechanism,
            kind="mechanism",
            tier="pro",
            enabled=False,
            status="license_invalid",
            reason="The detected license has not validated through the released runtime.",
        )

    features = {str(item) for item in status.get("features", [])}
    if mechanism not in features:
        return _entry(
            mechanism,
            kind="mechanism",
            tier="pro",
            enabled=False,
            status="feature_not_granted",
            reason=(
                "The validated license and active CLI build do not make this "
                "exact feature executable."
            ),
        )
    return _entry(
        mechanism,
        kind="mechanism",
        tier="pro",
        enabled=True,
        status="available",
        reason="The exact feature is granted for an explicit submitted run.",
    )


def inspect_reasoning_engine_availability(
    license_status: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Build entitlement/runtime state without executing or scenario-filtering engines."""

    return [
        _entry(
            "clips",
            kind="mechanism",
            tier="community",
            enabled=True,
            status="available",
            reason="Community CLIPS is available for an explicit submitted run.",
        ),
        _entry(
            "bn",
            kind="mechanism",
            tier="community",
            enabled=True,
            status="available",
            reason="Community Bayesian inference is available for an explicit submitted run.",
        ),
        _pro_entry("solver", license_status),
        _pro_entry("zen", license_status),
        _entry(
            "claims-audit",
            kind="mechanism",
            tier="community",
            enabled=True,
            status="available",
            reason="Synthetic administrative review is available after Analyze.",
        ),
    ]


def reasoning_engine_options(
    scenario: str,
    availability: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Add presentation-only scenario applicability to safe availability entries."""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")

    options = []
    for entry in availability:
        engine_id = str(entry.get("id", ""))
        if engine_id not in REASONING_ENGINES:
            continue
        enabled = entry.get("enabled") is True
        applicable = scenario in ENGINE_SCENARIOS[engine_id]
        if not enabled:
            emphasis = "unavailable"
            tooltip = str(entry.get("reason", "This engine is unavailable."))
        elif not applicable:
            emphasis = "unsupported_for_scenario"
            tooltip = (
                "Available and selectable, but this Reasoning Engine is not applied "
                "to the selected scenario."
            )
        else:
            emphasis = "normal"
            tooltip = str(entry.get("reason", "Available after Analyze."))
        options.append(
            {
                "id": engine_id,
                "label": ENGINE_LABELS[engine_id],
                "tier": str(entry.get("tier", "community")),
                "enabled": enabled,
                "applicable": applicable,
                "emphasis": emphasis,
                "tooltip": tooltip,
            }
        )
    return options


def inspect_mechanism_availability(
    scenario: str, license_status: Mapping[str, object] | None = None
) -> list[dict[str, object]]:
    """Compatibility adapter for the current Marimo cell graph."""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    return inspect_reasoning_engine_availability(license_status)
