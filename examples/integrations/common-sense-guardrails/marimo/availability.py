"""Fail-closed, import-safe availability for the Common Sense Workbench."""

from __future__ import annotations

from collections.abc import Callable, Mapping


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
BN_SCENARIOS = {"coupon-stack", "cold-chain"}
SOLVER_SCENARIOS = {"car-wash", "pallet-door"}
ZEN_SCENARIOS = {"coupon-stack", "cold-chain"}


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
    *,
    endpoint_probe: Callable[[str], bool] | None = None,
) -> list[dict[str, object]]:
    """Build selectable provider state without returning or validating secret values.

    Local endpoint probing is opt-in through an injected bounded probe. Importing or
    calling this function without one never opens a socket, starts a service, or
    downloads a model.
    """

    entries: list[dict[str, object]] = []
    for provider_id, credential_name in CLOUD_PROVIDERS:
        detected = credential_name in environ
        entries.append(
            _entry(
                provider_id,
                kind="provider",
                tier="community",
                enabled=detected,
                status="available" if detected else "credential_not_detected",
                reason=(
                    "Credential name detected; a provider call still requires explicit "
                    "Analyze submission."
                    if detected
                    else f"{credential_name} was not detected."
                ),
            )
        )

    for provider_id in LOCAL_PROVIDERS:
        reachable = endpoint_probe(provider_id) if endpoint_probe is not None else False
        entries.append(
            _entry(
                provider_id,
                kind="provider",
                tier="community",
                enabled=reachable,
                status="available" if reachable else "endpoint_unreachable",
                reason=(
                    "Bounded local endpoint/model preflight succeeded."
                    if reachable
                    else "Bounded local endpoint/model preflight has not succeeded."
                ),
            )
        )
    return entries


def _pro_entry(
    mechanism: str,
    compatible: bool,
    license_status: Mapping[str, object] | None,
) -> dict[str, object]:
    if not compatible:
        return _entry(
            mechanism,
            kind="mechanism",
            tier="pro",
            enabled=False,
            status="unsupported_for_scenario",
            reason="This mechanism is not applicable to the selected scenario.",
        )

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
            reason="The validated license does not grant this exact feature.",
        )
    return _entry(
        mechanism,
        kind="mechanism",
        tier="pro",
        enabled=True,
        status="available",
        reason="The exact feature is granted for an explicit submitted run.",
    )


def inspect_mechanism_availability(
    scenario: str, license_status: Mapping[str, object] | None = None
) -> list[dict[str, object]]:
    """Build scenario-compatible mechanism state without executing a mechanism."""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    if scenario == "synthetic-claims-audit":
        return [
            _entry(
                "claims-audit",
                kind="mechanism",
                tier="community",
                enabled=True,
                status="available",
                reason="Synthetic administrative review is available after Analyze.",
            )
        ]

    entries = [
        _entry(
            "clips",
            kind="mechanism",
            tier="community",
            enabled=True,
            status="available",
            reason="Community CLIPS is supported for an explicit submitted run.",
        ),
        _entry(
            "bn",
            kind="mechanism",
            tier="community",
            enabled=scenario in BN_SCENARIOS,
            status="available"
            if scenario in BN_SCENARIOS
            else "unsupported_for_scenario",
            reason=(
                "Community Bayesian review is applicable to this scenario."
                if scenario in BN_SCENARIOS
                else "Bayesian review is not applicable to this scenario."
            ),
        ),
    ]
    entries.append(_pro_entry("solver", scenario in SOLVER_SCENARIOS, license_status))
    entries.append(_pro_entry("zen", scenario in ZEN_SCENARIOS, license_status))
    return entries
