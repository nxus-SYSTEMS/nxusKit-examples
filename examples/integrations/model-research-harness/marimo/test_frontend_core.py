"""Tests for the explicit submitted-evaluation boundary."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "marimo" / "frontend_core.py"


def load_core():
    assert CORE.is_file(), "missing Model Research submitted-evaluation adapter"
    spec = importlib.util.spec_from_file_location("research_frontend_core", CORE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def request(**updates: object) -> dict[str, object]:
    base: dict[str, object] = {
        "config_id": "nxuskit-harness-basic.yaml",
        "mode": "mock",
        "provider": None,
        "model": None,
        "include_tests": [],
        "exclude_tests": [],
        "allow_external": False,
        "write_reports": False,
    }
    return {**base, **updates}


def test_unsubmitted_evaluation_has_no_runner_or_writer_effect(monkeypatch) -> None:
    """Catches a reactive input change executing the canonical harness."""

    core = load_core()
    calls: list[str] = []
    monkeypatch.setattr(core, "run_config", lambda *args, **kwargs: calls.append("run"))
    monkeypatch.setattr(
        core, "write_reports", lambda *args, **kwargs: calls.append("write")
    )
    result = core.run_evaluation(request(), submitted=False)
    assert result["report"] is None
    assert calls == []


def test_mock_request_delegates_to_the_existing_runner_without_writing() -> None:
    """Catches a frontend that forks report or scoring authority."""

    result = load_core().run_evaluation(request(), submitted=True)
    assert result["report"]["config_id"] == "basic-ticket-routing"
    assert result["report"]["final_status"] == "pass"
    assert result["report_path"] is None


def test_lifecycle_config_is_rejected_before_any_runner_call(monkeypatch) -> None:
    """Catches lifecycle mutation becoming reachable through an interactive request."""

    core = load_core()
    monkeypatch.setattr(
        core, "run_config", lambda *args, **kwargs: pytest.fail("runner invoked")
    )
    with pytest.raises(ValueError, match="Lifecycle mutation"):
        core.run_evaluation(
            request(config_id="nxuskit-harness-lifecycle-mutation-fixture.yaml"),
            submitted=True,
        )


def test_external_adapter_requires_submitted_acknowledgement() -> None:
    """Catches an external adapter running without the dedicated trust input."""

    with pytest.raises(ValueError, match="allow_external"):
        load_core().run_evaluation(
            request(config_id="nxuskit-harness-external-command-fixture.yaml"),
            submitted=True,
        )


def test_unavailable_provider_is_rejected_before_the_runner_is_called(
    monkeypatch,
) -> None:
    """Catches a disabled provider becoming runnable by a crafted UI request."""

    core = load_core()
    monkeypatch.setattr(
        core, "run_config", lambda *args, **kwargs: pytest.fail("runner invoked")
    )
    with pytest.raises(ValueError, match="not available"):
        core.run_evaluation(
            request(provider="openai"),
            submitted=True,
            provider_availability=[{"id": "openai", "enabled": False}],
        )
