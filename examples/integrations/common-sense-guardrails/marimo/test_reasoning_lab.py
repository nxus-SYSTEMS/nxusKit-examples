"""Contract tests for the ordinary-Python Marimo reasoning-lab frontend."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "marimo" / "reasoning_lab.py"
CORE = ROOT / "marimo" / "frontend_core.py"
PYTHON_ROOT = ROOT / "python"
REPO_ROOT = ROOT.parents[2]


def load_frontend():
    spec = importlib.util.spec_from_file_location("reasoning_lab", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_core():
    spec = importlib.util.spec_from_file_location("frontend_core", CORE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_import_exposes_an_ordinary_marimo_app_without_running_analysis() -> None:
    frontend = load_frontend()
    assert frontend.app is not None
    response = load_core().analyze_request(
        scenario="cold-chain", selected_guardrails=("clips", "bn"), analyze=False
    )
    assert response["record"] is None
    assert response["mode"] == "fixture"
    assert "Analyze" in response["message"]


def test_fixture_community_request_matches_the_canonical_cold_chain_record() -> None:
    frontend = load_core()
    sys.path.insert(0, str(PYTHON_ROOT))
    from main import build_reasoning_record

    response = frontend.analyze_request(
        scenario="cold-chain", selected_guardrails=("clips", "bn"), analyze=True
    )
    assert response["record"] == build_reasoning_record(
        "cold-chain", "mock", "ce", "clips,bn"
    )
    assert response["record"]["provenance"]["mode"] == "fixture"


def test_claims_frontend_path_is_offline_and_review_oriented() -> None:
    frontend = load_core()
    response = frontend.analyze_request(
        scenario="synthetic-claims-audit",
        selected_guardrails=("claims-audit",),
        analyze=True,
    )
    assert response["record"]["scenario"]["id"] == "synthetic-claims-audit"
    assert response["record"]["final"]["review_disposition"] == "review_required"
    assert response["pro_availability"] == []


def test_explicit_pro_selection_degrades_truthfully_without_a_pro_invocation() -> None:
    frontend = load_core()
    response = frontend.analyze_request(
        scenario="cold-chain", selected_guardrails=("clips", "zen"), analyze=True
    )
    assert response["record"] is not None
    assert response["effective_guardrails"] == ["clips"]
    assert response["pro_availability"] == [
        {
            "id": "zen",
            "tier": "pro",
            "selected": True,
            "available": False,
            "reason": "The fixture frontend does not invoke Pro mechanisms.",
        }
    ]


def test_script_mode_requires_an_explicit_analyze_flag() -> None:
    idle = subprocess.run(
        [sys.executable, str(CORE), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(idle.stdout)["record"] is None

    analyzed = subprocess.run(
        [
            sys.executable,
            str(CORE),
            "--json",
            "--analyze",
            "--scenario",
            "synthetic-claims-audit",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert (
        json.loads(analyzed.stdout)["record"]["scenario"]["id"]
        == "synthetic-claims-audit"
    )


def test_manifest_registers_the_frontend_without_changing_language_parity() -> None:
    manifest = json.loads(
        (REPO_ROOT / "conformance" / "examples_manifest.json").read_text()
    )
    entry = next(
        item
        for item in manifest["examples"]
        if item["name"] == "common-sense-guardrails"
    )
    assert entry["languages"] == ["python", "bash"]
    assert entry["frontends"] == [
        {
            "id": "reasoning-lab",
            "kind": "marimo",
            "language": "python",
            "entrypoint": "examples/integrations/common-sense-guardrails/marimo/reasoning_lab.py",
            "documentation": "examples/integrations/common-sense-guardrails/marimo/README.md",
            "default_mode": "fixture",
            "community_offline": True,
            "requires_explicit_analyze": True,
        }
    ]


def test_phase_two_selector_exposes_exactly_the_five_approved_scenarios() -> None:
    """Catches a workbench selector that silently omits an approved scenario."""

    assert load_core().SCENARIOS == (
        "car-wash",
        "coupon-stack",
        "pallet-door",
        "cold-chain",
        "synthetic-claims-audit",
    )


def test_unsubmitted_phase_two_request_invokes_no_canonical_runner(monkeypatch) -> None:
    """Catches reactive configuration changes that execute a runner before Analyze."""

    frontend = load_core()
    invoked: list[object] = []
    monkeypatch.setattr(
        frontend, "build_reasoning_record", lambda *args, **kwargs: invoked.append(args)
    )
    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["clips"],
            "max_repair_attempts": 3,
        },
        submitted=False,
    )
    assert response["record"] is None
    assert invoked == []


def test_submitted_fixture_request_preserves_canonical_record_identity() -> None:
    """Catches a frontend implementation that creates a second fixture authority."""

    frontend = load_core()
    response = frontend.analyze_request(
        {
            "scenario": "cold-chain",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["clips", "bn"],
            "max_repair_attempts": 3,
        },
        submitted=True,
    )
    assert response["record"] == frontend.build_reasoning_record(
        "cold-chain", "mock", None, "clips,bn", 3
    )


def test_submitted_live_request_delegates_with_scoped_provider_and_model(
    monkeypatch,
) -> None:
    """Catches dropped live request fields or provider state that persists after a run."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []

    def canonical_runner(*args):
        calls.append(
            (*args, os.environ.get("NXUSKIT_PROVIDER"), os.environ.get("NXUSKIT_MODEL"))
        )
        return {"canonical": True}

    monkeypatch.delenv("NXUSKIT_PROVIDER", raising=False)
    monkeypatch.delenv("NXUSKIT_MODEL", raising=False)
    monkeypatch.setattr(frontend, "build_reasoning_record", canonical_runner)
    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "live",
            "provider": "ollama",
            "model": "fixture-model",
            "mechanisms": ["clips"],
            "max_repair_attempts": 2,
        },
        submitted=True,
        provider_availability=[{"id": "ollama", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )
    assert response["record"] == {"canonical": True}
    assert calls == [("car-wash", "live", None, "clips", 2, "ollama", "fixture-model")]
    assert "NXUSKIT_PROVIDER" not in os.environ
    assert "NXUSKIT_MODEL" not in os.environ


def test_disabled_live_selection_fails_before_the_canonical_runner(monkeypatch) -> None:
    """Catches a disabled provider or mechanism reaching an effectful run boundary."""

    frontend = load_core()
    invoked: list[object] = []
    monkeypatch.setattr(
        frontend, "build_reasoning_record", lambda *args: invoked.append(args)
    )
    request = {
        "scenario": "cold-chain",
        "mode": "live",
        "provider": "openai",
        "model": "fixture-model",
        "mechanisms": ["clips"],
        "max_repair_attempts": 3,
    }
    with pytest.raises(ValueError, match="disabled provider"):
        frontend.analyze_request(
            request,
            submitted=True,
            provider_availability=[{"id": "openai", "enabled": False}],
            mechanism_availability=[{"id": "clips", "enabled": True}],
        )
    assert invoked == []


def test_phase_two_ui_has_one_form_boundary_and_plain_inspectable_result_surface() -> (
    None
):
    """Catches a reactive UI without a visible, explicit Analyze contract."""

    source = SCRIPT.read_text(encoding="utf-8")
    assert ".form(" in source
    assert 'submit_button_label="Analyze"' in source
    for label in (
        "Scenario",
        "Run mode",
        "Provider",
        "Model",
        "Mechanisms",
        "Repair attempts",
        "Summary",
        "Provider / model",
        "Mechanism execution",
        "Visual Evidence",
        "Findings",
        "Evidence",
        "Attempts",
        "Facts",
        "Raw JSON",
    ):
        assert label in source
    assert "inspect_provider_availability" in source
    assert "inspect_mechanism_availability" in source
    assert "disabled=True" in source
    assert "record_tables" in source
    assert "mo.ui.altair_chart" in source
    assert "mo.hstack" in source
    assert "wrap=True" in source
    assert "mo.vstack" in source
