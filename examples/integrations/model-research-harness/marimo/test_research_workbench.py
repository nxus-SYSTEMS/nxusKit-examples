"""Static UI contract tests for the safe Model Research Marimo workbench."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "marimo" / "workbench_contract.py"
APP = ROOT / "marimo" / "research_workbench.py"


def load_contract() -> ModuleType:
    assert MODULE.is_file(), "missing Model Research workbench UI contract"
    spec = importlib.util.spec_from_file_location(
        "model_research_workbench_contract", MODULE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_checked_in_config_is_visible_and_lifecycle_is_disabled() -> None:
    """Catches a UI catalog silently hiding a checked-in or unsafe config."""

    contract = load_contract()
    controls = contract.workbench_controls()
    assert set(controls["configs"]) == {
        path.name for path in (ROOT / "configs").glob("*.yaml")
    }
    lifecycle = controls["configs"]["nxuskit-harness-lifecycle-mutation-fixture.yaml"]
    assert lifecycle["visible"] is True
    assert lifecycle["enabled"] is False
    assert "Lifecycle mutation is unavailable" in lifecycle["reason"]


def test_unavailable_providers_remain_visible_with_a_reason() -> None:
    """Catches disabled availability being confused with hidden availability."""

    controls = load_contract().workbench_controls(environ={})
    openai = controls["providers"]["openai"]
    assert openai["visible"] is True
    assert openai["enabled"] is False
    assert "OPENAI_API_KEY" in openai["reason"]


def test_disabled_config_and_provider_reasons_have_visible_text_evidence() -> None:
    """Catches a disabled option being hidden behind an inaccessible control."""

    contract = load_contract()
    availability = contract.availability_markdown(
        contract.workbench_controls(environ={})
    )
    assert "nxuskit-harness-lifecycle-mutation-fixture.yaml" in availability
    assert "Lifecycle mutation is unavailable from this frontend." in availability
    assert "`openai`" in availability
    assert "OPENAI_API_KEY is not detected." in availability


def test_contract_has_one_submit_boundary_and_all_inspection_surfaces() -> None:
    """Catches an effectful control or an incomplete evidence view."""

    controls = load_contract().workbench_controls()
    assert controls["primary_action"] == {
        "id": "run-evaluation",
        "label": "Run evaluation",
    }
    assert controls["modes"] == [
        "mock",
        "auto",
        "live",
        "dry-run-policy",
        "import-promptfoo",
    ]
    assert {
        "Summary",
        "Visual Evidence",
        "Results",
        "Confidence",
        "Capability Truth",
        "Policy",
        "Raw JSON",
    } <= set(controls["inspection_sections"])
    assert {
        "config_id",
        "mode",
        "provider",
        "model",
        "include_tests",
        "exclude_tests",
        "allow_external",
    } <= set(controls["form_fields"])
    source = APP.read_text(encoding="utf-8")
    assert source.count('submit_button_label="Run evaluation"') == 1
