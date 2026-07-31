"""Pure Polars and Altair projections for canonical reasoning records."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import altair as alt


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
PRESENTER_PATH = ROOT / "marimo" / "presenters.py"


def load_presenters() -> ModuleType:
    """Load the presentation boundary so absence is a deliberate red failure."""

    assert PRESENTER_PATH.is_file(), "missing pure Polars/Altair presenter module"
    spec = importlib.util.spec_from_file_location(
        "reasoning_presenters", PRESENTER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cold_chain_record() -> dict[str, object]:
    sys.path.insert(0, str(PYTHON_ROOT))
    from main import build_reasoning_record

    return build_reasoning_record("cold-chain", "mock", None, "clips,bn", 3)


def synthetic_claims_record() -> dict[str, object]:
    sys.path.insert(0, str(PYTHON_ROOT))
    from claims_audit import build_claims_reasoning_record

    return build_claims_reasoning_record()


def test_tables_project_canonical_findings_attempts_mechanisms_facts_and_evidence() -> (
    None
):
    """Catches a presenter that loses an inspectable canonical record section."""

    tables = load_presenters().record_tables(cold_chain_record())
    assert set(tables) >= {
        "stages",
        "findings",
        "attempts",
        "mechanisms",
        "facts",
        "evidence",
    }
    assert {"mechanism_id", "status", "severity", "rule_id"} <= set(
        tables["findings"].columns
    )
    assert {"number", "status", "selected_mechanisms"} <= set(
        tables["attempts"].columns
    )
    assert {"id", "availability", "runtime_executed"} <= set(
        tables["mechanisms"].columns
    )
    assert tables["findings"].height > 0
    assert tables["stages"].to_dicts()[-1]["stage"] == "final review"


def test_charts_include_truthful_stage_and_finding_category_projections() -> None:
    """Catches missing stage, severity, or mechanism evidence in the visual layer."""

    charts = load_presenters().chart_specs(cold_chain_record())
    with alt.data_transformers.enable("default", consolidate_datasets=False):
        stages = charts["stage_progression"].to_dict()["data"]["values"]
        findings = charts["findings_by_category"].to_dict()["data"]["values"]
    assert stages[0] == {"attempt": 1, "stage": "baseline", "status": "pass"}
    assert stages[-1]["stage"] == "final review"
    assert {"mechanism_id", "severity", "status", "count"} <= set(findings[0])


def test_bn_chart_uses_the_final_observed_probability_and_threshold() -> None:
    """Catches a chart that invents or swaps the final BN probability/threshold."""

    charts = load_presenters().chart_specs(cold_chain_record())
    with alt.data_transformers.enable("default", consolidate_datasets=False):
        values = charts["bn_threshold"].to_dict()["data"]["values"]
    assert values == [
        {"metric": "observed_probability", "value": 0.08},
        {"metric": "review_threshold", "value": 0.5},
    ]


def test_empty_or_inapplicable_sections_stay_labeled_and_uncharted() -> None:
    """Catches empty result handling that raises or fabricates numeric evidence."""

    empty = {
        "mechanisms": [],
        "findings": [],
        "facts": [],
        "evidence": [],
        "attempts": [],
    }
    presenters = load_presenters()
    tables = presenters.record_tables(empty)
    assert tables["findings"].height == 0
    assert {"mechanism_id", "status", "severity", "rule_id"} <= set(
        tables["findings"].columns
    )
    assert "bn_threshold" not in presenters.chart_specs(empty)


def test_synthetic_claims_project_exception_categories_and_bounded_profile_labels() -> (
    None
):
    """Catches a claims view that hides audit categories or overstates scale."""

    tables = load_presenters().record_tables(synthetic_claims_record())
    assert tables["claims_exception_categories"].height > 0
    assert set(tables["claims_exception_categories"].columns) == {
        "rule_id",
        "severity",
        "count",
    }
    assert tables["claims_scale_profiles"].to_dicts() == [
        {"profile": "1k", "row_count": 1_000},
        {"profile": "100k", "row_count": 100_000},
        {"profile": "1m", "row_count": 1_000_000},
    ]


def test_chart_serialization_excludes_fact_values_and_secret_like_content() -> None:
    """Catches chart data that exposes unrelated fact or prompt content."""

    record = cold_chain_record()
    record["facts"].append(
        {
            "id": "fact-private-note",
            "type": "private_note",
            "value": "canary-prompt-secret",
            "source": "fixture",
            "confidence": 1.0,
        }
    )
    serialized = json.dumps(
        {
            name: chart.to_dict()
            for name, chart in load_presenters().chart_specs(record).items()
        },
        sort_keys=True,
    )
    assert "canary-prompt-secret" not in serialized
