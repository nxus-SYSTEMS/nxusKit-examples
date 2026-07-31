"""Explicit submitted-evaluation adapter for the canonical Model Research harness."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from config_catalog import build_config_catalog  # noqa: E402
from harness.config import ConfigError, load_config  # noqa: E402
from harness.promptfoo_import import import_promptfoo  # noqa: E402
from harness.reports import build_report, write_reports  # noqa: E402
from harness.runner import run_config  # noqa: E402
from main import filter_tests  # noqa: E402


OUTPUT_ROOT = ROOT / ".tmp" / "model-research-workbench"
MODES = {"mock", "auto", "live", "dry-run-policy", "import-promptfoo"}


def _catalog_entry(config_id: str) -> Mapping[str, object]:
    for entry in build_config_catalog(ROOT):
        if entry["id"] == config_id:
            return entry
    raise ValueError("unknown checked-in config")


def _request_value(request: Mapping[str, object], name: str) -> object:
    if name not in request:
        raise ValueError(f"request missing {name}")
    return request[name]


def _filter_values(value: object) -> list[str]:
    """Normalize widget text without accidentally expanding it character by character."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(
        isinstance(item, str) for item in value
    ):
        return list(value)
    raise ValueError("test filters must be text or a list of text values")


def _require_available_provider(
    provider: object, availability: Sequence[Mapping[str, object]] | None
) -> None:
    if not provider or availability is None:
        return
    provider_id = str(provider)
    entry = next((item for item in availability if item.get("id") == provider_id), None)
    if entry is None or entry.get("enabled") is not True:
        raise ValueError("requested provider is not available")


def run_evaluation(
    request: Mapping[str, object],
    *,
    submitted: bool,
    provider_availability: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Run one canonical harness evaluation only after explicit submission."""

    config_id = str(_request_value(request, "config_id"))
    mode = str(_request_value(request, "mode"))
    if mode not in MODES:
        raise ValueError("unsupported evaluation mode")
    allow_external = bool(_request_value(request, "allow_external"))
    write_requested = bool(_request_value(request, "write_reports"))
    entry = _catalog_entry(config_id)
    if not submitted:
        return {
            "report": None,
            "report_path": None,
            "message": "Configure inputs, then press Run evaluation.",
        }
    if entry["enabled"] is not True:
        raise ValueError(str(entry["reason"]))
    if entry["category"] == "external-adapter" and not allow_external:
        raise ValueError("external adapter requires allow_external=true")
    _require_available_provider(
        _request_value(request, "provider"), provider_availability
    )

    config_path = ROOT / "configs" / config_id
    if not config_path.is_file() or config_path.parent != ROOT / "configs":
        raise ValueError("config must be a checked-in config file")
    compatibility: dict[str, Any] | None = None
    if mode == "import-promptfoo":
        config, compatibility = import_promptfoo(config_path, allow_code=False)
        if config is None:
            return {
                "report": None,
                "report_path": None,
                "compatibility_report": compatibility or {},
                "message": "Promptfoo config requires a separate explicit trust decision.",
            }
    else:
        try:
            config = load_config(config_path)
        except ConfigError as exc:
            raise ValueError(f"config unavailable for this mode: {exc}") from exc
        config["_config_dir"] = str(config_path.parent)

    include = _filter_values(_request_value(request, "include_tests"))
    exclude = _filter_values(_request_value(request, "exclude_tests"))
    filter_tests(config, include=include, exclude=exclude)
    runner_mode = "mock" if mode in {"dry-run-policy", "import-promptfoo"} else mode
    results, bayesian, recommendations, truth = run_config(
        config,
        mode=runner_mode,
        provider_override=_request_value(request, "provider") or None,
        model_override=_request_value(request, "model") or None,
        output_dir=OUTPUT_ROOT,
        allow_external_commands=allow_external,
        allow_lifecycle_mutations=False,
    )
    report = build_report(
        config, results, bayesian, recommendations, truth, compatibility
    )
    report_path: str | None = None
    if write_requested:
        run_root = OUTPUT_ROOT / uuid.uuid4().hex
        run_root.resolve().relative_to(OUTPUT_ROOT.resolve())
        write_reports(report, run_root)
        report_path = str(run_root / "result.json")
    return {
        "report": report,
        "report_path": report_path,
        "message": "Canonical report built after explicit Run evaluation.",
    }
