"""Behavioral tests for released-cli-only MRH provider model discovery."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("model_catalog.py")


def load_catalog():
    assert MODULE_PATH.is_file(), "missing Model Research model catalog adapter"
    spec = importlib.util.spec_from_file_location("model_catalog", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingRunner:
    def __init__(self, *payloads: dict[str, object]):
        self.payloads = iter(payloads)
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs: object):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(next(self.payloads)), stderr=""
        )


def test_ollama_catalog_uses_only_released_cli_read_commands() -> None:
    catalog = load_catalog()
    runner = RecordingRunner(
        {
            "result": {
                "models": [
                    {
                        "id": "qwen3.5:4b",
                        "name": "qwen3.5:4b",
                        "provider": "ollama",
                        "supports": ["chat", "streaming"],
                        "context_window": 32768,
                        "local": True,
                    }
                ]
            }
        },
        {"result": {"models": [{"id": "qwen3.5:4b", "name": "Qwen local model"}]}},
    )

    result = catalog.discover_provider_models(
        "ollama", runner=runner, environ={"NXUSKIT_CLI": "/sdk/bin/nxuskit-cli"}
    )

    assert [call[0] for call in runner.calls] == [
        [
            "/sdk/bin/nxuskit-cli",
            "models",
            "--provider",
            "ollama",
            "--format",
            "json",
            "--local-only",
        ],
        [
            "/sdk/bin/nxuskit-cli",
            "provider",
            "info",
            "ollama",
            "--json",
        ],
    ]
    assert result.state == "ready"
    assert result.models[0].id == "qwen3.5:4b"
    assert result.models[0].description == "Qwen local model"
