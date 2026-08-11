"""Behavior and source-boundary tests for the Model Research sibling controls."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


MODULE_PATH = Path(__file__).with_name("workbench_controls.py")
JS_PATH = Path(__file__).with_name("workbench_controls.js")
CSS_PATH = Path(__file__).with_name("workbench_controls.css")


def load_controls() -> ModuleType:
    assert MODULE_PATH.is_file(), "missing Model Research AnyWidget bridge"
    spec = importlib.util.spec_from_file_location("workbench_controls", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def snapshot(provider: str, state: str = "loading", *, models=()):
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

    def request(self, provider, *, force=False):
        self.requests.append((provider, force))
        return snapshot(provider)

    def poll(self, provider):
        self.polls.append(provider)
        model = SimpleNamespace(
            id="qwen3.5:4b",
            name="Qwen 3.5 4B",
            provider=provider,
            supports=("chat", "streaming"),
            context_window=32768,
            local=True,
            description="Local multilingual model",
        )
        return snapshot(provider, "ready", models=(model,))


def test_widget_starts_local_discovery_in_parallel_and_enables_ollama() -> None:
    """Catches the old MRH path that permanently marked Ollama unreachable."""

    module = load_controls()
    coordinator = FakeCoordinator()
    widget = module.WorkbenchControls(coordinator=coordinator, environ={})

    assert coordinator.requests == [("ollama", False), ("lmstudio", False)]
    widget.selected_provider = "ollama"
    widget.poll_generation += 1

    ollama = next(item for item in widget.providers if item["id"] == "ollama")
    assert ollama["enabled"] is True
    assert widget.models[0]["id"] == "qwen3.5:4b"
    assert widget.submit_generation == 0
    assert widget.submitted_request == {}


def test_widget_keeps_credential_values_out_of_synced_state() -> None:
    module = load_controls()
    canary = "must-never-reach-widget-state"
    widget = module.WorkbenchControls(
        coordinator=FakeCoordinator(), environ={"ANTHROPIC_API_KEY": canary}
    )

    claude = next(item for item in widget.providers if item["id"] == "claude")
    assert claude["enabled"] is True
    assert canary not in str(widget.trait_values())


def test_widget_uses_fixture_as_the_user_facing_mock_mode_label() -> None:
    """Catches internal mock vocabulary leaking into the user-facing mode control."""

    widget = load_controls().WorkbenchControls(
        coordinator=FakeCoordinator(), environ={}
    )

    fixture = next(mode for mode in widget.modes if mode["id"] == "mock")
    assert fixture == {
        "id": "mock",
        "label": "Fixture",
        "message": "Deterministic synthetic evidence; no provider call.",
    }


def test_widget_source_matches_reasoning_lab_visual_and_effect_boundaries() -> None:
    assert JS_PATH.is_file(), "missing Model Research DOM renderer"
    assert CSS_PATH.is_file(), "missing Model Research control styles"
    source = JS_PATH.read_text(encoding="utf-8")

    assert "Configure the Workbench ..." in source
    assert source.index("Configuration and Mode") < source.index("Provider and Model")
    assert source.index("Provider and Model") < source.index("Evaluation Configuration")
    assert "Fixture — deterministic synthetic evidence" in source
    assert "Auto — may attempt a compatible enabled live provider" in source
    assert "Live — runs the selected enabled provider" in source
    assert "Unavailable configs" not in source
    assert "Availability and execution truth" not in source
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource"):
        assert forbidden not in source
