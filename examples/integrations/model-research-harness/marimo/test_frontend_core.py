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


def test_live_override_replaces_a_checked_in_loopback_provider(monkeypatch) -> None:
    """Catches Live/Claude controls silently returning the config's mock fixture."""

    load_core()
    from harness import providers

    calls: list[tuple[str | None, str | None]] = []
    monkeypatch.setattr(
        providers,
        "call_live_provider",
        lambda _provider, _test, _prompt, provider_override, model_override: (
            calls.append((provider_override, model_override))
            or {
                "content": '{"label":"billing"}',
                "source": "live",
                "model": model_override,
                "metadata": {},
            }
        ),
    )

    result = providers.call_provider(
        {"id": "local-fixture", "provider": "loopback", "model": "fixture-v1"},
        {
            "id": "ticket",
            "prompt": "Classify {{ ticket }}",
            "vars": {"ticket": "synthetic duplicate charge"},
            "mock_response": {"label": "fixture"},
        },
        "live",
        provider_override="claude",
        model_override="claude-sonnet-4-6",
    )

    assert calls == [("claude", "claude-sonnet-4-6")]
    assert result["source"] == "live"
    assert result["model"] == "claude-sonnet-4-6"


def test_live_results_use_the_effective_provider_identity(monkeypatch) -> None:
    """Catches a Claude result and capability row mislabeled as local-fixture."""

    load_core()
    from harness import runner

    monkeypatch.setattr(
        runner,
        "call_provider",
        lambda *_args, **_kwargs: {
            "content": '{"label":"billing"}',
            "source": "live",
            "provider_id": "claude",
            "model": "claude-sonnet-4-6",
            "metadata": {},
        },
    )
    config = {
        "id": "synthetic-live-identity",
        "providers": [
            {
                "id": "local-fixture",
                "provider": "loopback",
                "model": "fixture-v1",
                "capabilities": {
                    "json_mode": True,
                    "tool_calling": "emulated",
                },
            }
        ],
        "tests": [
            {
                "id": "ticket",
                "prompt": "Classify synthetic ticket",
                "provider_ids": ["local-fixture"],
                "assertions": [{"type": "is-json"}],
            }
        ],
    }

    results, _bayesian, _recommendations, truth = runner.run_config(
        config,
        mode="live",
        provider_override="claude",
        model_override="claude-sonnet-4-6",
    )

    assert results[0]["provider_id"] == "claude"
    assert truth[0]["provider_id"] == "claude"
    assert truth[0]["provider"] == "claude"
    assert truth[0]["model"] == "claude-sonnet-4-6"
    assert truth[0]["json_mode"] is False
    assert truth[0]["tool_calling"] == "unavailable"


def test_basic_live_prompt_declares_the_exact_label_vocabulary() -> None:
    """Catches a strict label assertion whose accepted values are absent from the prompt."""

    core = load_core()
    config = core.load_config(core.ROOT / "configs" / "nxuskit-harness-basic.yaml")
    prompt = config["tests"][0]["prompt"]

    assert "exactly one of" in prompt
    assert '"billing"' in prompt
    assert '"technical"' in prompt
    assert '"account"' in prompt
    assert '"other"' in prompt


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


def test_live_mode_requires_an_explicit_provider_and_model(monkeypatch) -> None:
    """Catches Live silently using the checked-in loopback fixture or fixture model."""

    core = load_core()
    monkeypatch.setattr(
        core, "run_config", lambda *args, **kwargs: pytest.fail("runner invoked")
    )
    available = [{"id": "claude", "enabled": True}]

    with pytest.raises(ValueError, match="Live mode requires an enabled provider"):
        core.run_evaluation(
            request(mode="live", provider=None, model=None),
            submitted=True,
            provider_availability=available,
        )
    with pytest.raises(
        ValueError, match="selected provider requires an explicit model"
    ):
        core.run_evaluation(
            request(mode="live", provider="claude", model=None),
            submitted=True,
            provider_availability=available,
        )


def test_auto_selected_provider_requires_an_explicit_model(monkeypatch) -> None:
    """Catches Auto sending a checked-in fixture model ID to a cloud provider."""

    core = load_core()
    monkeypatch.setattr(
        core, "run_config", lambda *args, **kwargs: pytest.fail("runner invoked")
    )

    with pytest.raises(
        ValueError, match="selected provider requires an explicit model"
    ):
        core.run_evaluation(
            request(mode="auto", provider="claude", model=None),
            submitted=True,
            provider_availability=[{"id": "claude", "enabled": True}],
        )
    with pytest.raises(
        ValueError, match="selected provider requires an explicit model"
    ):
        core.run_evaluation(
            request(mode="auto", provider="claude", model="   "),
            submitted=True,
            provider_availability=[{"id": "claude", "enabled": True}],
        )
