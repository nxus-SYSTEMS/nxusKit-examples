"""Import-safe catalog of the checked-in Model Research configurations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from harness.config import list_config_paths, load_data  # noqa: E402


def _category(config: dict[str, Any], filename: str) -> tuple[str, bool, str]:
    """Classify existing config structure without running its adapters."""

    tests = config.get("tests") or []
    external = any(
        isinstance(test, dict)
        and str(test.get("adapter", "")).replace("-", "_") == "external_command"
        for test in tests
    )
    lifecycle = any(
        isinstance(test, dict)
        and bool((test.get("external_command") or {}).get("mutation"))
        for test in tests
    )
    if lifecycle:
        return (
            "lifecycle-sensitive",
            False,
            "Lifecycle mutation is unavailable from this frontend.",
        )
    if filename.startswith("promptfoo-"):
        return (
            "promptfoo",
            True,
            "Promptfoo compatibility is imported only after explicit submission.",
        )
    if external:
        return (
            "external-adapter",
            True,
            "External adapters require a separately submitted allow_external acknowledgement.",
        )
    if (config.get("policy") or {}).get("engine") or (config.get("bayesian") or {}).get(
        "engine"
    ):
        return (
            "engine-backed",
            True,
            "Engine execution remains behind explicit submitted evaluation.",
        )
    return ("safe-built-in", True, "Offline fixture evaluation is available.")


def _expanded_test_count(config: dict[str, Any]) -> int:
    """Count the concrete test variants represented by a configuration."""

    count = 0
    for test in config.get("tests") or []:
        matrix = test.get("matrix") if isinstance(test, dict) else None
        variants = 1
        if isinstance(matrix, dict):
            for values in matrix.values():
                variants *= len(values) if isinstance(values, list) and values else 1
        count += variants
    return count


def _configured_engines(config: dict[str, Any]) -> list[str]:
    """Return only reasoning engines explicitly selected by this config."""

    engines = []
    if (config.get("policy") or {}).get("engine") == "nxuskit-clips":
        engines.append("clips")
    if (config.get("bayesian") or {}).get("engine") == "nxuskit-bn":
        engines.append("bn")
    return engines


def build_config_catalog(root: Path = ROOT) -> list[dict[str, object]]:
    """Return every checked-in config exactly once with safe UI truth fields."""

    catalog = []
    for path in list_config_paths(root):
        config = load_data(path)
        category, enabled, reason = _category(config, path.name)
        catalog.append(
            {
                "id": path.name,
                "filename": path.name,
                "label": str(config.get("id") or path.stem),
                "description": str(
                    config.get("description") or "No description supplied."
                ),
                "test_count": _expanded_test_count(config),
                "configured_engines": _configured_engines(config),
                "category": category,
                "visible": True,
                "enabled": enabled,
                "reason": reason,
            }
        )
    return catalog
