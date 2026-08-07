"""Behavioral tests for SDK-only provider and model discovery."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType


MODULE_PATH = Path(__file__).with_name("provider_catalog.py")


def load_catalog() -> ModuleType:
    assert MODULE_PATH.is_file(), "missing released nxusKit provider catalog adapter"
    spec = importlib.util.spec_from_file_location("provider_catalog", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingRunner:
    def __init__(self, *payloads: dict[str, object]):
        self.payloads = iter(payloads)
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(next(self.payloads)), stderr=""
        )


def models_payload() -> dict[str, object]:
    return {
        "trace_id": "safe-ignored-trace",
        "result": {
            "models": [
                {
                    "id": "qwen3.5:4b",
                    "name": "qwen3.5:4b",
                    "provider": "ollama",
                    "supports": ["chat", "streaming", "unrecognized-capability"],
                    "context_window": None,
                    "local": True,
                }
            ]
        },
    }


def provider_info_payload() -> dict[str, object]:
    return {
        "result": {
            "name": "ollama",
            "models": [
                {
                    "id": "qwen3.5:4b",
                    "name": "Qwen: multilingual model for local deployment",
                }
            ],
        }
    }


def test_ollama_catalog_uses_only_released_cli_read_commands() -> None:
    """Catches discovery bypassing the released CLI or dropping safe metadata."""

    catalog = load_catalog()
    runner = RecordingRunner(models_payload(), provider_info_payload())

    result = catalog.discover_provider_models(
        "ollama", runner=runner, environ={"NXUSKIT_CLI": "/sdk/bin/nxuskit-cli"}
    )

    assert runner.calls == [
        (
            [
                "/sdk/bin/nxuskit-cli",
                "models",
                "--provider",
                "ollama",
                "--format",
                "json",
                "--local-only",
            ],
            {"text": True, "capture_output": True, "check": False, "timeout": 6},
        ),
        (
            [
                "/sdk/bin/nxuskit-cli",
                "provider",
                "info",
                "ollama",
                "--json",
            ],
            {"text": True, "capture_output": True, "check": False, "timeout": 6},
        ),
    ]
    assert result.state == "ready"
    assert len(result.models) == 1
    assert result.models[0].id == "qwen3.5:4b"
    assert result.models[0].supports == ("chat", "streaming")
    assert result.models[0].description == (
        "Qwen: multilingual model for local deployment"
    )
    assert result.models[0].context_window is None


def test_catalog_never_serializes_environment_values_or_cli_diagnostics() -> None:
    """Catches credential or subprocess diagnostic leakage through discovery state."""

    catalog = load_catalog()
    canary = "canary-secret-value"

    def failing_runner(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=f"provider rejected {canary} with trace secret-trace",
        )

    result = catalog.discover_provider_models(
        "openai", runner=failing_runner, environ={"OPENAI_API_KEY": canary}
    )
    serialized = json.dumps(dataclasses.asdict(result), sort_keys=True)

    assert result.state == "failed"
    assert result.message == "Model discovery was unavailable."
    assert canary not in serialized
    assert "secret-trace" not in serialized


def test_provider_reachability_uses_released_cli_ping_contract() -> None:
    """Catches local readiness using a raw endpoint or the wrong v1.0.5 JSON shape."""

    catalog = load_catalog()
    runner = RecordingRunner(
        {
            "latency_ms": 12.5,
            "models_found": 1,
            "provider": "ollama",
            "reachable": True,
        }
    )

    assert (
        catalog.provider_reachable(
            "ollama", runner=runner, environ={"NXUSKIT_CLI": "/sdk/bin/nxuskit-cli"}
        )
        is True
    )
    assert runner.calls == [
        (
            [
                "/sdk/bin/nxuskit-cli",
                "provider",
                "ping",
                "--provider",
                "ollama",
                "--json",
                "--timeout",
                "750",
            ],
            {"text": True, "capture_output": True, "check": False, "timeout": 6},
        )
    ]


def test_catalog_timeout_returns_a_stable_safe_failure() -> None:
    """Catches timeout details escaping or discovery waiting without a bound."""

    catalog = load_catalog()

    def timeout_runner(command: list[str], **_kwargs: object):
        raise subprocess.TimeoutExpired(command, timeout=6, output="secret-output")

    result = catalog.discover_provider_models(
        "ollama", runner=timeout_runner, environ={}
    )

    assert result.state == "failed"
    assert result.models == ()
    assert result.message == "Model discovery timed out."
