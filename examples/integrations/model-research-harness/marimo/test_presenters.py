"""Pure Polars and Altair projection tests for Model Research reports."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import altair as alt


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
MODULE = ROOT / "marimo" / "presenters.py"


def load_presenters() -> ModuleType:
    assert MODULE.is_file(), "missing pure Model Research presenter module"
    spec = importlib.util.spec_from_file_location("research_presenters", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def mock_report() -> dict[str, object]:
    sys.path.insert(0, str(PYTHON_ROOT))
    from harness.config import load_config
    from harness.reports import build_report
    from harness.runner import run_config

    config_path = ROOT / "configs" / "nxuskit-harness-basic.yaml"
    config = load_config(config_path)
    config["_config_dir"] = str(config_path.parent)
    results, bayesian, recommendations, truth = run_config(config, mode="mock")
    return build_report(config, results, bayesian, recommendations, truth)


def test_tables_project_results_policy_confidence_capability_and_failures() -> None:
    """Catches report sections vanishing from the inspectable analysis surface."""

    tables = load_presenters().report_tables(mock_report())
    assert {"results", "policy", "confidence", "capabilities", "failures"} <= set(
        tables
    )
    assert {"test_id", "provider_id", "model", "status", "score"} <= set(
        tables["results"].columns
    )
    assert tables["results"].height == 1
    assert tables["failures"].height == 0


def test_charts_include_truthful_scores_confidence_and_capability_matrix() -> None:
    """Catches chart data replacing the canonical report with invented metrics."""

    charts = load_presenters().report_charts(mock_report())
    assert {
        "provider_test_heatmap",
        "score_ranking",
        "pass_fail",
        "confidence",
        "capability_truth",
    } <= set(charts)
    with alt.data_transformers.enable("default", consolidate_datasets=False):
        values = charts["score_ranking"].to_dict()["data"]["values"]
    assert values == [{"provider_id": "local-fixture", "score": 1.0}]


def test_absent_latency_token_and_cost_are_never_invented() -> None:
    """Catches misleading measured-performance charts for fields the report lacks."""

    presenters = load_presenters()
    tables = presenters.report_tables(mock_report())
    charts = presenters.report_charts(mock_report())
    assert "latency_ms" not in tables["results"].columns
    assert not {"latency", "tokens", "cost"} & set(charts)
