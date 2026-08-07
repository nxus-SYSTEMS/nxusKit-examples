"""Behavior and source-boundary tests for the Reasoning Lab control surface."""

from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path
from types import ModuleType, SimpleNamespace


MODULE_PATH = Path(__file__).with_name("reasoning_controls.py")
JS_PATH = Path(__file__).with_name("reasoning_controls.js")
CSS_PATH = Path(__file__).with_name("reasoning_controls.css")


def load_controls() -> ModuleType:
    assert MODULE_PATH.is_file(), "missing Reasoning Lab AnyWidget bridge"
    spec = importlib.util.spec_from_file_location("reasoning_controls", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def catalog_model(model_id: str = "qwen3.5:4b") -> SimpleNamespace:
    return SimpleNamespace(
        id=model_id,
        name=model_id,
        provider="ollama",
        supports=("chat", "streaming"),
        context_window=None,
        local=True,
        description="Qwen model family",
    )


def discovery_snapshot(
    provider: str, state: str = "loading", *, models=()
) -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        state=state,
        models=tuple(models),
        message="Models ready." if state == "ready" else "Loading models.",
    )


class FakeCoordinator:
    def __init__(self):
        self.requests: list[tuple[str, bool]] = []
        self.polls: list[str] = []
        self.analysis_calls: list[object] = []

    def request(self, provider, *, force=False):
        self.requests.append((provider, force))
        return discovery_snapshot(provider)

    def poll(self, provider):
        self.polls.append(provider)
        return discovery_snapshot(provider, "ready", models=(catalog_model(),))


def fully_entitled_engine_availability() -> list[dict[str, object]]:
    return [
        {
            "id": engine,
            "enabled": True,
            "tier": "pro" if engine in {"solver", "zen"} else "community",
            "reason": "Available after Analyze.",
        }
        for engine in ("clips", "bn", "solver", "zen", "claims-audit")
    ]


def option(options, engine_id):
    return next(item for item in options if item["id"] == engine_id)


def test_widget_defaults_and_parallel_local_startup() -> None:
    """Catches missing defaults or sequential/omitted local model discovery."""

    module = load_controls()
    coordinator = FakeCoordinator()

    widget = module.ReasoningControls(coordinator=coordinator, environ={})

    assert widget.scenario == "cold-chain"
    assert widget.mode == "fixture"
    assert widget.selected_engines == ["clips", "bn"]
    assert widget.submit_generation == 0
    assert widget.submitted_request == {}
    assert coordinator.requests == [("ollama", False), ("lmstudio", False)]


def test_provider_change_requests_discovery_and_refresh_forces_only_selected() -> None:
    """Catches reactive selection invoking analysis or refreshing another provider."""

    module = load_controls()
    coordinator = FakeCoordinator()
    widget = module.ReasoningControls(coordinator=coordinator, environ={})
    coordinator.requests.clear()

    widget.selected_provider = "ollama"
    widget.refresh_generation += 1

    assert coordinator.requests == [("ollama", False), ("ollama", True)]
    assert coordinator.analysis_calls == []
    assert widget.submit_generation == 0
    assert widget.submitted_request == {}


def test_scenario_change_updates_applicability_without_losing_selection() -> None:
    """Catches scenario reactivity clearing enabled but temporarily unsupported engines."""

    module = load_controls()
    widget = module.ReasoningControls(
        coordinator=FakeCoordinator(),
        environ={},
        engine_availability=fully_entitled_engine_availability(),
    )
    widget.selected_engines = ["clips", "bn", "solver", "zen"]

    widget.scenario = "car-wash"

    assert widget.selected_engines == ["clips", "bn", "solver", "zen"]
    assert option(widget.engines, "solver")["applicable"] is True
    assert option(widget.engines, "zen")["applicable"] is False
    assert option(widget.engines, "zen")["emphasis"] == "unsupported_for_scenario"


def test_claims_scenario_returns_mode_to_fixture_without_running_analysis() -> None:
    """Catches a prior Live selection lingering on the offline claims audit."""

    module = load_controls()
    widget = module.ReasoningControls(
        coordinator=FakeCoordinator(),
        environ={},
        engine_availability=fully_entitled_engine_availability(),
    )
    widget.mode = "live"

    widget.scenario = "synthetic-claims-audit"

    assert widget.mode == "fixture"
    assert widget.submit_generation == 0
    assert widget.submitted_request == {}


def test_coupon_scenario_disables_live_and_provider_discovery_without_contact() -> None:
    """Catches coupon scenario reactivity triggering discovery or retaining Live."""

    module = load_controls()
    coordinator = FakeCoordinator()
    widget = module.ReasoningControls(
        coordinator=coordinator,
        environ={"ANTHROPIC_API_KEY": "credential-value-is-never-retained"},
        engine_availability=fully_entitled_engine_availability(),
    )
    widget.mode = "live"
    widget.selected_provider = "claude"
    coordinator.requests.clear()

    widget.scenario = "coupon-stack"

    assert widget.mode == "auto"
    assert option(widget.modes, "live")["enabled"] is False
    assert coordinator.requests == []
    assert all(provider["selectable"] is False for provider in widget.providers)


def test_trait_updates_use_only_current_observer_api_without_deprecation() -> None:
    """Catches observer names that traitlets treats as deprecated magic methods."""

    module = load_controls()
    widget = module.ReasoningControls(coordinator=FakeCoordinator(), environ={})

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        widget.scenario = "car-wash"


def test_late_result_for_previous_provider_cannot_replace_selected_models() -> None:
    """Catches a stale provider result overwriting the newly selected provider's UI."""

    module = load_controls()
    widget = module.ReasoningControls(coordinator=FakeCoordinator(), environ={})
    widget.selected_provider = "ollama"
    widget.selected_provider = "openai"

    widget.apply_discovery_snapshot(
        discovery_snapshot("ollama", "ready", models=(catalog_model(),))
    )

    assert widget.selected_provider == "openai"
    assert widget.models == []


def test_poll_updates_models_without_advancing_analyze_generation() -> None:
    """Catches background catalog completion triggering an effectful submitted run."""

    module = load_controls()
    coordinator = FakeCoordinator()
    widget = module.ReasoningControls(coordinator=coordinator, environ={})
    widget.selected_provider = "ollama"

    widget.poll_generation += 1

    assert [item["id"] for item in widget.models] == ["qwen3.5:4b"]
    assert widget.submit_generation == 0
    assert widget.submitted_request == {}
    assert coordinator.analysis_calls == []


def test_widget_source_has_approved_layout_copy_and_no_provider_network_path() -> None:
    """Catches removed copy returning or browser JavaScript contacting providers."""

    assert JS_PATH.is_file(), "missing AnyWidget DOM renderer"
    source = JS_PATH.read_text(encoding="utf-8")

    assert "Choose Scenario and Configure Reasoning ..." in source
    assert source.index("Scenario and Mode") < source.index("Provider and Model")
    assert source.index("Provider and Model") < source.index("Reasoning Engines")
    assert (
        "Fixture — deterministic synthetic evidence; it does not call a provider."
        in source
    )
    assert "Auto — may attempt a compatible enabled live provider" in source
    assert "Live — runs the selected enabled provider." in source
    assert "Unavailable providers (disabled)" not in source
    assert "Unavailable mechanisms (disabled)" not in source
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
        assert forbidden not in source


def test_widget_rearms_background_polling_until_cloud_discovery_is_terminal() -> None:
    """Catches a completed cloud catalog remaining hidden until another UI change."""

    source = JS_PATH.read_text(encoding="utf-8")
    watched = source.split("const watched = [", 1)[1].split("];", 1)[0]

    assert '"poll_generation"' in watched


def test_mode_guidance_is_an_accessible_visible_tooltip() -> None:
    """Catches reliance on a delayed native title tooltip and help cursor alone."""

    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    assert 'tooltip.setAttribute("role", "tooltip")' in source
    assert 'info.setAttribute("aria-describedby"' in source
    assert 'info.addEventListener("focus"' in source
    assert 'info.addEventListener("click"' in source
    assert "mode-tooltip" in css


def test_claims_fixture_constraint_uses_compact_accessible_badge() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    assert "Fixture-only · no LLM" in source
    assert 'badge.setAttribute("role", "note")' in source
    assert "This deterministic synthetic data-quality audit" in source
    assert "mode-note" not in source
    assert "scenario-mode-grid" in css


def test_analyze_gate_uses_available_applicable_explicit_selection() -> None:
    source = JS_PATH.read_text(encoding="utf-8")

    assert "hasSelectedApplicableEngine" in source
    assert "Select at least one available Reasoning Engine" in source


def test_analyze_control_exposes_indeterminate_progress_and_completion_traits() -> None:
    """Catches Analyze appearing inert while a provider or local engine is running."""

    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")
    module = load_controls()
    widget = module.ReasoningControls(coordinator=FakeCoordinator(), environ={})

    assert widget.completed_generation == 0
    assert widget.completed_elapsed_ms == 0
    assert widget.completion_state == "idle"
    assert 'status.setAttribute("role", "status")' in source
    assert 'status.setAttribute("aria-live", "polite")' in source
    assert "analysis-spinner" in source
    assert "analysis-spinner" in css


def test_running_elapsed_display_truncates_to_whole_seconds() -> None:
    """Catches a noisy fractional-second counter while analysis is in progress."""

    source = JS_PATH.read_text(encoding="utf-8")

    assert 'activeRun.phase === "running"' in source
    assert "function formatElapsed(milliseconds, includeMilliseconds)" in source
    assert "Math.floor(runElapsedSeconds()) * 1000" in source
    assert "formatElapsed(activeElapsedMs, false)" in source
    assert 'formatElapsed(model.get("completed_elapsed_ms"), true)' in source
    assert "runElapsedSeconds().toFixed(1)" not in source
    assert "window.setInterval(updateRunStatusText, 1000)" in source
    assert '(model.get("completed_elapsed_ms") / 1000).toFixed(3)' not in source


def test_new_run_discloses_that_prior_completed_results_remain_below() -> None:
    """Catches a stale final status appearing to describe the active run."""

    source = JS_PATH.read_text(encoding="utf-8")

    assert 'model.get("completed_generation") > 0' in source
    assert (
        "Previous completed results remain visible below until this run finishes."
        in source
    )


def test_status_attempts_and_analyze_share_one_status_first_action_row() -> None:
    """Catches the live status consuming a second vertical row below Analyze."""

    source = JS_PATH.read_text(encoding="utf-8")
    action_source = source.split('const actionRow = element("div", "action-row")', 1)[1]

    status_position = action_source.index("actionRow.appendChild(status)")
    attempts_position = action_source.index("actionRow.appendChild(attempts)")
    analyze_position = action_source.index("actionRow.appendChild(analyze)")
    assert status_position < attempts_position < analyze_position
    assert "Maximum repair attempts" in action_source
    assert (
        "One initial response plus up to this many repaired responses." in action_source
    )


def test_repair_attempts_sync_on_input_before_analyze() -> None:
    """Catches a displayed attempt count differing from the submitted request."""

    source = JS_PATH.read_text(encoding="utf-8")

    assert 'attemptsInput.addEventListener("input"' in source
    assert "Number.isInteger(value) && value >= 1 && value <= 10" in source


def test_fixture_llm_smoke_override_disables_provider_backed_modes() -> None:
    """Catches a deterministic smoke launch presenting Auto or Live as truthful."""

    module = load_controls()
    widget = module.ReasoningControls(
        coordinator=FakeCoordinator(),
        environ={"NXUSKIT_COMMON_SENSE_FIXTURE_LLM": "1"},
    )
    source = JS_PATH.read_text(encoding="utf-8")

    assert widget.fixture_llm_override is True
    assert "Provider-backed modes are disabled" in source
    assert "option.disabled = modeDisabledForState(" in source
    assert 'model.get("scenario") === "coupon-stack"' in source
    assert 'model.get("modes") || []' in source


def test_widget_source_encodes_disabled_applicability_refresh_and_submit_contracts() -> (
    None
):
    """Catches controls that cannot express state or submit an immutable snapshot."""

    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    assert "providerButton.disabled = presentation.disabled" in source
    assert '"scenario-inapplicable"' in source
    assert "checkbox.disabled = !engine.enabled" in source
    assert 'engine.emphasis === "unsupported_for_scenario"' in source
    assert "refresh_generation" in source
    assert 'model.set("submitted_request", buildSubmittedRequest({' in source
    assert 'const nextGeneration = model.get("submit_generation") + 1' in source
    assert 'model.set("submit_generation", nextGeneration)' in source
    assert "unsupported-for-scenario" in css
    assert "provider-button.scenario-inapplicable" in css
    assert "font-style: italic" in css
    assert "@media (max-width: 720px)" in css
