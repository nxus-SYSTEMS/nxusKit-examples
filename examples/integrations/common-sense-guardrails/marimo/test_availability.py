"""Behavioral tests for the Common Sense Workbench availability boundary."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


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


def snapshot(state: str, *, has_models: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        state=state,
        models=(object(),) if has_models else (),
        message="Safe discovery state.",
    )


def test_local_provider_discovery_states_are_visible_and_fail_closed() -> None:
    """Catches pending, empty, or failed local catalogs becoming selectable."""

    module = load_availability()
    for state, has_models, expected_status in (
        ("idle", False, "runtime_unavailable"),
        ("loading", False, "runtime_unavailable"),
        ("empty", False, "runtime_unavailable"),
        ("failed", False, "endpoint_unreachable"),
    ):
        entries = module.inspect_provider_availability(
            {}, {"ollama": snapshot(state, has_models=has_models)}
        )
        ollama = entry(entries, "ollama")
        assert ollama["visible"] is True
        assert ollama["enabled"] is False
        assert ollama["status"] == expected_status


def test_ready_or_retained_stale_local_catalog_is_enabled() -> None:
    """Catches usable SDK-reported local models remaining disabled."""

    module = load_availability()
    for state in ("ready", "stale"):
        entries = module.inspect_provider_availability(
            {}, {"ollama": snapshot(state, has_models=True)}
        )
        ollama = entry(entries, "ollama")
        assert ollama["enabled"] is True
        assert ollama["status"] == "available"


def test_cloud_catalog_state_combines_with_value_blind_credential_detection() -> None:
    """Catches a credential name overriding an empty catalog or leaking discovery data."""

    module = load_availability()
    canary = "canary-openai-secret"
    empty_entries = module.inspect_provider_availability(
        {"OPENAI_API_KEY": canary}, {"openai": snapshot("empty")}
    )
    stale_entries = module.inspect_provider_availability(
        {"OPENAI_API_KEY": canary},
        {"openai": snapshot("stale", has_models=True)},
    )

    assert entry(empty_entries, "openai")["enabled"] is False
    assert entry(empty_entries, "openai")["status"] == "runtime_unavailable"
    assert entry(stale_entries, "openai")["enabled"] is True
    assert entry(stale_entries, "openai")["status"] == "available"
    assert canary not in json.dumps([empty_entries, stale_entries], sort_keys=True)
    assert "Safe discovery state." not in json.dumps(
        [empty_entries, stale_entries], sort_keys=True
    )


def test_all_reasoning_engines_stay_visible_and_entitlement_is_scenario_independent() -> (
    None
):
    """Catches scenario filtering that hides an entitled engine from the selector."""

    module = load_availability()
    availability = module.inspect_reasoning_engine_availability(
        {"token_detected": True, "validated": True, "features": ["solver", "zen"]}
    )

    assert [item["id"] for item in availability] == [
        "clips",
        "bn",
        "solver",
        "zen",
        "claims-audit",
    ]
    options = module.reasoning_engine_options("car-wash", availability)
    assert entry(options, "solver")["enabled"] is True
    assert entry(options, "solver")["applicable"] is True
    assert entry(options, "zen")["enabled"] is True
    assert entry(options, "zen")["applicable"] is False
    assert entry(options, "zen")["emphasis"] == "unsupported_for_scenario"


def test_unlicensed_engine_is_disabled_even_when_scenario_applicable() -> None:
    """Catches applicability incorrectly overriding a missing Pro entitlement."""

    module = load_availability()
    availability = module.inspect_reasoning_engine_availability(
        {"token_detected": True, "validated": True, "features": []}
    )

    solver = entry(module.reasoning_engine_options("car-wash", availability), "solver")
    assert solver["enabled"] is False
    assert solver["applicable"] is True
    assert solver["emphasis"] == "unavailable"


def test_token_presence_alone_never_enables_optional_pro_mechanisms() -> None:
    """Catches a Solver or ZEN enablement decision based on token presence alone."""

    module = load_availability()
    entries = module.inspect_reasoning_engine_availability(
        license_status={"token_detected": True, "validated": False, "features": []},
    )
    solver = entry(entries, "solver")
    assert solver["visible"] is True
    assert solver["enabled"] is False
    assert solver["status"] == "license_invalid"
    zen = entry(entries, "zen")
    assert zen["enabled"] is False
    assert zen["status"] == "license_invalid"
    assert (
        entry(module.reasoning_engine_options("car-wash", entries), "zen")["applicable"]
        is False
    )


def test_only_an_exact_validated_feature_grant_enables_a_supported_mechanism() -> None:
    """Catches incorrect feature-grant or scenario-compatibility handling for Pro."""

    module = load_availability()
    entries = module.inspect_reasoning_engine_availability(
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
    assert solver["status"] == "feature_not_granted"
    assert (
        entry(module.reasoning_engine_options("cold-chain", entries), "solver")[
            "applicable"
        ]
        is False
    )


def test_released_license_status_accepts_released_valid_pro_feature_names() -> None:
    """Catches a license adapter that leaks payloads or grants unallowlisted features."""

    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_cli_runner(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "cli": {"pro_engines_compiled": True},
                    "license": {
                        "effective_edition": "pro",
                        "status": "valid",
                        "features": ["solver", "zen", "unrelated-pro-feature"],
                    },
                }
            ),
            stderr="",
        )

    status = load_availability().released_license_status(
        runner=fake_cli_runner, environ={"NXUSKIT_CLI": "nxuskit-cli"}
    )

    assert status == {
        "token_detected": True,
        "validated": True,
        "features": ["solver", "zen"],
    }
    assert calls == [
        (
            ["nxuskit-cli", "license", "status", "--json"],
            {"text": True, "capture_output": True, "check": False, "timeout": 10},
        )
    ]


def test_valid_pro_license_does_not_enable_engines_missing_from_cli_build() -> None:
    """Catches an OSS CLI enabling Pro controls from token grants alone."""

    module = load_availability()
    status = module.released_license_status(
        runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "cli": {"pro_engines_compiled": False},
                    "license": {
                        "edition": "oss",
                        "effective_edition": "pro",
                        "status": "valid",
                        "features": ["solver", "zen"],
                    },
                }
            ),
            stderr="",
        ),
        environ={"NXUSKIT_CLI": "nxuskit-cli"},
    )
    zen = entry(module.inspect_reasoning_engine_availability(status), "zen")

    assert status == {
        "token_detected": True,
        "validated": True,
        "features": [],
    }
    assert zen["visible"] is True
    assert zen["enabled"] is False
    assert zen["status"] == "feature_not_granted"


def test_released_license_status_fails_closed_for_malformed_invalid_or_non_pro_status() -> (
    None
):
    """Catches malformed CLI output or an invalid license enabling Pro controls."""

    module = load_availability()
    malformed = module.released_license_status(
        runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["nxuskit-cli"], 0, stdout="not-json", stderr=""
        ),
        environ={"NXUSKIT_CLI": "nxuskit-cli"},
    )
    invalid = module.released_license_status(
        runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["nxuskit-cli"],
            0,
            stdout=json.dumps(
                {
                    "license": {
                        "effective_edition": "pro",
                        "status": "invalid",
                        "features": ["solver"],
                    }
                }
            ),
            stderr="",
        ),
        environ={"NXUSKIT_CLI": "nxuskit-cli"},
    )
    non_pro = module.released_license_status(
        runner=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["nxuskit-cli"],
            0,
            stdout=json.dumps(
                {
                    "license": {
                        "effective_edition": "community",
                        "status": "valid",
                        "features": ["solver"],
                    }
                }
            ),
            stderr="",
        ),
        environ={"NXUSKIT_CLI": "nxuskit-cli"},
    )

    assert malformed == {"token_detected": False, "validated": False, "features": []}
    assert invalid == {"token_detected": True, "validated": False, "features": []}
    assert non_pro == {"token_detected": True, "validated": False, "features": []}


def test_coupon_mode_options_keep_fixture_auto_and_disable_live() -> None:
    options = load_availability().scenario_mode_options("coupon-stack")

    assert [item["id"] for item in options] == ["fixture", "auto", "live"]
    assert [item["enabled"] for item in options] == [True, True, False]
    assert entry(options, "auto")["resolved_mode"] == "fixture"
    assert entry(options, "live")["compatibility_code"] == (
        "coupon_live_strict_schema_transport_unavailable_v1_0_5"
    )


def test_coupon_provider_projection_preserves_global_availability() -> None:
    base = [{"id": "claude", "enabled": True, "status": "available", "reason": "ready"}]

    projected = load_availability().provider_options_for_scenario("coupon-stack", base)

    assert projected[0]["enabled"] is True
    assert projected[0]["status"] == "available"
    assert projected[0]["reason"] == "ready"
    assert projected[0]["applicable"] is False
    assert projected[0]["selectable"] is False


def test_non_coupon_provider_projection_preserves_selectability() -> None:
    base = [
        {"id": "claude", "enabled": True, "status": "available", "reason": "ready"},
        {
            "id": "openai",
            "enabled": False,
            "status": "credential_not_detected",
            "reason": "missing",
        },
    ]

    projected = load_availability().provider_options_for_scenario("car-wash", base)

    assert all(item["applicable"] is True for item in projected)
    assert [item["selectable"] for item in projected] == [True, False]
