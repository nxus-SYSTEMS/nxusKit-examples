"""Safe availability inspection for the Model Research Workbench."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping


CLOUD_PROVIDERS = (
    ("claude", "ANTHROPIC_API_KEY"),
    ("openai", "OPENAI_API_KEY"),
    ("groq", "GROQ_API_KEY"),
    ("xai", "XAI_API_KEY"),
)
LOCAL_PROVIDERS = ("ollama", "lmstudio")
RELEASED_PRO_FEATURES = ("solver", "zen")


def _empty_license_status() -> dict[str, object]:
    return {"token_detected": False, "validated": False, "features": []}


def released_license_status(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Project released CLI license status into the safe availability contract."""

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
    return {
        "token_detected": token_detected,
        "validated": True,
        "features": [
            feature
            for feature in RELEASED_PRO_FEATURES
            if pro_engines_compiled and isinstance(granted, list) and feature in granted
        ],
    }


def _entry(
    entry_id: str,
    *,
    kind: str,
    tier: str,
    enabled: bool,
    status: str,
    reason: str,
    runtime_executed: bool = False,
) -> dict[str, object]:
    return {
        "id": entry_id,
        "kind": kind,
        "tier": tier,
        "visible": True,
        "enabled": enabled,
        "status": status,
        "reason": reason,
        "runtime_executed": runtime_executed,
    }


def inspect_provider_availability(
    environ: Mapping[str, str],
    *,
    endpoint_probe: Callable[[str], bool] | None = None,
) -> list[dict[str, object]]:
    """Inspect only credential names; probe local endpoints only when injected."""

    entries = []
    for provider, credential_name in CLOUD_PROVIDERS:
        detected = credential_name in environ
        entries.append(
            _entry(
                provider,
                kind="provider",
                tier="community",
                enabled=detected,
                status="available" if detected else "credential_not_detected",
                reason=(
                    "Credential name detected; execution still requires explicit submission."
                    if detected
                    else f"{credential_name} is not detected."
                ),
            )
        )
    for provider in LOCAL_PROVIDERS:
        reachable = endpoint_probe(provider) if endpoint_probe is not None else False
        entries.append(
            _entry(
                provider,
                kind="provider",
                tier="community",
                enabled=reachable,
                status="available" if reachable else "endpoint_unreachable",
                reason=(
                    "Bounded local endpoint preflight succeeded."
                    if reachable
                    else "Local endpoint has not passed a bounded preflight."
                ),
            )
        )
    return entries


def inspect_engine_availability(
    *,
    native_probe: Callable[[str], bool] | None = None,
    license_status: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Return fixture fallback truth unless an explicit native probe succeeds."""

    entries = []
    for engine in ("clips", "bn"):
        native_available = native_probe(engine) if native_probe is not None else False
        entries.append(
            _entry(
                engine,
                kind="engine",
                tier="community",
                enabled=True,
                status="available" if native_available else "runtime_unavailable",
                reason=(
                    "Bounded native runtime preflight succeeded."
                    if native_available
                    else "Offline fixture fallback is available; native runtime was not probed."
                ),
                runtime_executed=native_available,
            )
        )
    status = license_status or {}
    token_detected = bool(status.get("token_detected"))
    validated = bool(status.get("validated"))
    features = set(status.get("features") or [])
    for engine, feature in (("solver", "solver"), ("zen", "zen")):
        granted = validated and feature in features
        if not token_detected:
            availability_status = "license_not_detected"
            reason = "No validated released v1.0.5 license status is available."
        elif not validated:
            availability_status = "license_invalid"
            reason = (
                "The detected license has not validated through the released runtime."
            )
        elif not granted:
            availability_status = "feature_not_granted"
            reason = (
                "The validated license and active CLI build do not make this "
                "exact feature executable."
            )
        else:
            availability_status = "available"
            reason = "Validated v1.0.5 feature grant detected."
        entries.append(
            _entry(
                engine,
                kind="engine",
                tier="pro",
                enabled=granted,
                status=availability_status,
                reason=reason,
            )
        )
    return entries
