"""Behavioral tests for the Common Sense Workbench availability boundary."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


MODULE_PATH = Path(__file__).with_name("availability.py")


def load_availability() -> ModuleType:
    """Load the adapter explicitly so the missing implementation is a red failure."""

    assert MODULE_PATH.is_file(), "missing fail-closed availability adapter"
    spec = importlib.util.spec_from_file_location("workbench_availability", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def entry(entries: list[dict[str, object]], entry_id: str) -> dict[str, object]:
    return next(item for item in entries if item["id"] == entry_id)


def test_cloud_providers_are_visible_but_disabled_without_credentials() -> None:
    """Catches a UI that hides or enables cloud providers without their key name."""

    entries = load_availability().inspect_provider_availability({})
    for provider_id in ("claude", "openai", "groq", "xai"):
        provider = entry(entries, provider_id)
        assert provider["visible"] is True
        assert provider["enabled"] is False
        assert provider["status"] == "credential_not_detected"
        assert provider["runtime_executed"] is False


def test_cloud_credential_name_enables_without_serializing_its_value() -> None:
    """Catches an availability response that leaks a detected credential value."""

    canary = "canary-openai-credential-value"
    entries = load_availability().inspect_provider_availability(
        {"OPENAI_API_KEY": canary}
    )
    openai = entry(entries, "openai")
    assert openai["enabled"] is True
    assert openai["status"] == "available"
    serialized = json.dumps(entries, sort_keys=True)
    assert canary not in serialized
    assert "api_key" not in serialized


def test_local_provider_preflight_is_injected_and_fail_closed() -> None:
    """Catches a local provider that becomes selectable when its bounded probe fails."""

    calls: list[str] = []

    def unreachable(provider_id: str) -> bool:
        calls.append(provider_id)
        return False

    entries = load_availability().inspect_provider_availability(
        {}, endpoint_probe=unreachable
    )
    assert calls == ["ollama", "lmstudio"]
    for provider_id in calls:
        provider = entry(entries, provider_id)
        assert provider["visible"] is True
        assert provider["enabled"] is False
        assert provider["status"] == "endpoint_unreachable"


def test_token_presence_alone_never_enables_optional_pro_mechanisms() -> None:
    """Catches a Solver or ZEN enablement decision based on token presence alone."""

    entries = load_availability().inspect_mechanism_availability(
        "car-wash",
        license_status={"token_detected": True, "validated": False, "features": []},
    )
    solver = entry(entries, "solver")
    assert solver["visible"] is True
    assert solver["enabled"] is False
    assert solver["status"] == "license_invalid"
    zen = entry(entries, "zen")
    assert zen["enabled"] is False
    assert zen["status"] == "unsupported_for_scenario"


def test_only_an_exact_validated_feature_grant_enables_a_supported_mechanism() -> None:
    """Catches incorrect feature-grant or scenario-compatibility handling for Pro."""

    entries = load_availability().inspect_mechanism_availability(
        "cold-chain",
        license_status={"token_detected": True, "validated": True, "features": ["zen"]},
    )
    bn = entry(entries, "bn")
    assert bn["enabled"] is True
    assert bn["status"] == "available"
    zen = entry(entries, "zen")
    assert zen["enabled"] is True
    assert zen["status"] == "available"
    solver = entry(entries, "solver")
    assert solver["enabled"] is False
    assert solver["status"] == "unsupported_for_scenario"
