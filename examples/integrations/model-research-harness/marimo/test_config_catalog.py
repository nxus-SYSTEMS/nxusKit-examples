"""Contract tests for the safe Model Research config catalog."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[2]
CATALOG = ROOT / "marimo" / "config_catalog.py"
SCHEMA = (
    REPO_ROOT
    / "specs/013-interactive-reasoning-workbenches-v105/contracts/research-run-request.schema.json"
)


def load_catalog():
    assert CATALOG.is_file(), "missing pure Model Research config catalog"
    spec = importlib.util.spec_from_file_location("research_config_catalog", CATALOG)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_catalog_covers_every_checked_in_config_once() -> None:
    """Catches a checked-in config silently disappearing from the workbench."""

    catalog = load_catalog().build_config_catalog(ROOT)
    loaded = {path.name for path in load_catalog().list_config_paths(ROOT)}
    assert {entry["filename"] for entry in catalog} == loaded
    assert len(catalog) == len(loaded)


def test_catalog_disables_lifecycle_and_marks_external_or_promptfoo_truthfully() -> (
    None
):
    """Catches lifecycle mutation becoming reachable through a frontend option."""

    catalog = {
        entry["filename"]: entry for entry in load_catalog().build_config_catalog(ROOT)
    }
    lifecycle = catalog["nxuskit-harness-lifecycle-mutation-fixture.yaml"]
    assert lifecycle["category"] == "lifecycle-sensitive"
    assert lifecycle["visible"] is True
    assert lifecycle["enabled"] is False
    assert (
        lifecycle["reason"] == "Lifecycle mutation is unavailable from this frontend."
    )
    assert (
        catalog["nxuskit-harness-external-command-fixture.yaml"]["category"]
        == "external-adapter"
    )
    assert catalog["promptfoo-basic.yaml"]["category"] == "promptfoo"
    assert catalog["nxuskit-harness-bn-engine.yaml"]["category"] == "engine-backed"


def test_research_request_schema_has_only_safe_modes_and_no_lifecycle_field() -> None:
    """Catches a request contract that permits lifecycle mutation or unknown effects."""

    assert SCHEMA.is_file(), "missing research run-request schema"
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    request = {
        "config_id": "nxuskit-harness-basic.yaml",
        "mode": "mock",
        "provider": None,
        "model": None,
        "include_tests": [],
        "exclude_tests": [],
        "allow_external": False,
        "write_reports": False,
    }
    assert list(validator.iter_errors(request)) == []
    assert list(validator.iter_errors({**request, "mode": "unsafe"}))
    errors = list(validator.iter_errors({**request, "allow_lifecycle_mutations": True}))
    assert [error.validator for error in errors] == ["additionalProperties"]
    assert schema["properties"]["allow_external"]["default"] is False
    assert schema["properties"]["write_reports"]["default"] is False
