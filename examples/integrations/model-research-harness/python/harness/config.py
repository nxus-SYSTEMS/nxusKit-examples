"""Config loading for the model research harness example.

The bundled public configs are JSON-compatible YAML so the quickstart works with
the Python standard library. If PyYAML is installed, users can load a broader
YAML subset for their own configs.
"""

from __future__ import annotations

import json
from pathlib import Path
from itertools import product
from typing import Any


class ConfigError(ValueError):
    """Raised when a harness config is invalid."""


def load_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as json_exc:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigError(
                f"{path} is not JSON-compatible YAML; install PyYAML for broader YAML"
            ) from exc
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ConfigError(f"{path} must load to an object") from json_exc
        data = loaded
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain an object")
    return data


def load_config(path: Path) -> dict[str, Any]:
    config = load_data(path)
    expand_test_matrices(config)
    validate_config(config, path)
    return config


def expand_test_matrices(config: dict[str, Any]) -> None:
    expanded = []
    for test in config.get("tests") or []:
        matrix = test.get("matrix")
        if not matrix:
            expanded.append(test)
            continue
        keys = list(matrix)
        values = [
            matrix[key] if isinstance(matrix[key], list) else [matrix[key]]
            for key in keys
        ]
        for combo in product(*values):
            combo_vars = dict(zip(keys, combo))
            item = {key: value for key, value in test.items() if key != "matrix"}
            item["id"] = render_matrix_text(str(test["id"]), combo_vars)
            item["vars"] = {**(test.get("vars") or {}), **combo_vars}
            expanded.append(item)
    config["tests"] = expanded


def render_matrix_text(value: str, vars_: dict[str, Any]) -> str:
    for key, item in vars_.items():
        value = value.replace("{{ " + key + " }}", str(item)).replace(
            "{{" + key + "}}", str(item)
        )
    return value


def validate_config(config: dict[str, Any], path: Path) -> None:
    for key in ("id", "providers", "tests"):
        if key not in config:
            raise ConfigError(f"{path} missing required key: {key}")
    if not isinstance(config["providers"], list) or not config["providers"]:
        raise ConfigError(f"{path} providers must be a non-empty array")
    if not isinstance(config["tests"], list) or not config["tests"]:
        raise ConfigError(f"{path} tests must be a non-empty array")

    provider_ids = set()
    for provider in config["providers"]:
        if not isinstance(provider, dict):
            raise ConfigError(f"{path} provider entries must be objects")
        provider_id = provider.get("id")
        provider_name = provider.get("provider")
        if not provider_id or not provider_name:
            raise ConfigError(f"{path} provider entries require id and provider")
        provider_ids.add(provider_id)

    for test in config["tests"]:
        if not isinstance(test, dict):
            raise ConfigError(f"{path} test entries must be objects")
        adapter = str(test.get("adapter", "")).replace("-", "_")
        if not test.get("id"):
            raise ConfigError(f"{path} each test requires id")
        if not test.get("prompt") and adapter != "external_command":
            raise ConfigError(f"{path} each non-adapter test requires prompt")
        if adapter == "external_command" and "external_command" not in test:
            raise ConfigError(
                f"{path} external-command test {test['id']} requires external_command"
            )
        if "provider_ids" in test:
            missing = set(test["provider_ids"]) - provider_ids
            if missing:
                raise ConfigError(
                    f"{path} test {test['id']} unknown providers: {missing}"
                )


def list_config_paths(root: Path) -> list[Path]:
    return sorted((root / "configs").glob("*.yaml"))
