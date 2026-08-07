"""Availability truth tests for the Model Research Workbench."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "marimo" / "availability.py"


def load_availability():
    assert MODULE.is_file(), "missing Model Research availability adapter"
    spec = importlib.util.spec_from_file_location("research_availability", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cloud_entries_are_visible_disabled_and_secret_free_by_default() -> None:
    """Catches a hidden or credential-leaking cloud provider entry."""

    entries = load_availability().inspect_provider_availability({})
    assert [entry["id"] for entry in entries] == [
        "claude",
        "openai",
        "groq",
        "xai",
        "ollama",
        "lmstudio",
    ]
    assert all(
        entry["visible"] is True and entry["enabled"] is False for entry in entries
    )


def test_credential_name_enables_without_serializing_the_canary_value() -> None:
    """Catches an availability result exposing a credential value."""

    canary = "canary-groq-secret"
    entries = load_availability().inspect_provider_availability(
        {"GROQ_API_KEY": canary}
    )
    groq = next(entry for entry in entries if entry["id"] == "groq")
    assert groq["enabled"] is True
    assert canary not in json.dumps(entries, sort_keys=True)


def test_local_probes_are_explicit_and_engine_fixture_fallback_is_truthful() -> None:
    """Catches startup probes or absent native engines claimed as executed."""

    module = load_availability()
    calls: list[str] = []
    entries = module.inspect_provider_availability(
        {}, endpoint_probe=lambda name: calls.append(name) or name == "ollama"
    )
    assert calls == ["ollama", "lmstudio"]
    assert (
        next(entry for entry in entries if entry["id"] == "ollama")["enabled"] is True
    )
    engines = module.inspect_engine_availability(native_probe=lambda name: False)
    clips = next(entry for entry in engines if entry["id"] == "clips")
    assert clips["enabled"] is True
    assert clips["status"] == "runtime_unavailable"
    assert clips["runtime_executed"] is False


def test_pro_requires_a_validated_exact_feature_grant() -> None:
    """Catches token detection alone enabling Solver or ZEN."""

    engines = load_availability().inspect_engine_availability(
        license_status={"token_detected": True, "validated": False, "features": []}
    )
    assert all(
        entry["enabled"] is False
        for entry in engines
        if entry["id"] in {"solver", "zen"}
    )


def test_every_availability_entry_conforms_to_the_shared_contract() -> None:
    """Catches a workbench-only availability status outside the canonical schema."""

    module = load_availability()
    schema_path = (
        ROOT.parents[2]
        / "specs"
        / "013-interactive-reasoning-workbenches-v105"
        / "contracts"
        / "availability.schema.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text()))
    entries = (
        module.inspect_provider_availability({}) + module.inspect_engine_availability()
    )

    assert [error for entry in entries for error in validator.iter_errors(entry)] == []


def test_released_license_status_accepts_released_valid_pro_feature_names() -> None:
    """Catches an adapter that exposes raw license payloads or unknown features."""

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
    engines = module.inspect_engine_availability(license_status=status)
    pro = {item["id"]: item for item in engines if item["tier"] == "pro"}

    assert status == {
        "token_detected": True,
        "validated": True,
        "features": [],
    }
    assert pro["solver"]["enabled"] is False
    assert pro["zen"]["enabled"] is False
    assert pro["solver"]["status"] == "feature_not_granted"
    assert pro["zen"]["status"] == "feature_not_granted"


def test_released_license_status_fails_closed_for_malformed_invalid_or_non_pro_status() -> (
    None
):
    """Catches malformed or invalid status responses enabling Pro engines."""

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
                        "features": ["zen"],
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
                        "features": ["zen"],
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
