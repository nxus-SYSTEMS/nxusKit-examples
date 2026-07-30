"""Contract tests for the ordinary-Python Marimo reasoning-lab frontend."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


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
