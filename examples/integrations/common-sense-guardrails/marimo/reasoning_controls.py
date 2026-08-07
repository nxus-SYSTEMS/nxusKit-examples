"""AnyWidget bridge for the Reasoning Lab's pure configuration surface."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import anywidget
import traitlets

from availability import (
    CLOUD_PROVIDERS,
    inspect_provider_availability,
    inspect_reasoning_engine_availability,
    provider_options_for_scenario,
    reasoning_engine_options,
    scenario_mode_options,
)
from model_discovery import ProviderDiscoveryCoordinator


LOCAL_PROVIDERS = ("ollama", "lmstudio")
TERMINAL_DISCOVERY_STATES = {"ready", "empty", "stale", "failed"}


def _safe_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """Retain credential names only; never keep their values on the widget."""

    return {
        credential_name: "detected"
        for _provider, credential_name in CLOUD_PROVIDERS
        if credential_name in environ
    }


def _model_row(model: object) -> dict[str, object]:
    return {
        "id": str(getattr(model, "id", "")),
        "name": str(getattr(model, "name", "")),
        "provider": str(getattr(model, "provider", "")),
        "supports": list(getattr(model, "supports", ())),
        "context_window": getattr(model, "context_window", None),
        "local": getattr(model, "local", False) is True,
        "description": getattr(model, "description", None),
    }


class ReasoningControls(anywidget.AnyWidget):
    """Present configuration and emit immutable explicit-Analyze snapshots."""

    _esm = Path(__file__).with_name("reasoning_controls.js")
    _css = Path(__file__).with_name("reasoning_controls.css")

    scenario = traitlets.Unicode("cold-chain").tag(sync=True)
    mode = traitlets.Unicode("fixture").tag(sync=True)
    modes = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
    providers = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
    selected_provider = traitlets.Unicode(allow_none=True, default_value=None).tag(
        sync=True
    )
    models = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
    selected_model = traitlets.Unicode(allow_none=True, default_value=None).tag(
        sync=True
    )
    model_state = traitlets.Unicode("idle").tag(sync=True)
    model_message = traitlets.Unicode("Select a provider to discover models.").tag(
        sync=True
    )
    discovery_loading = traitlets.Bool(True).tag(sync=True)
    engines = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
    selected_engines = traitlets.List(
        trait=traitlets.Unicode(), default_value=["clips", "bn"]
    ).tag(sync=True)
    max_repair_attempts = traitlets.Int(3).tag(sync=True)
    refresh_generation = traitlets.Int(0).tag(sync=True)
    poll_generation = traitlets.Int(0).tag(sync=True)
    submit_generation = traitlets.Int(0).tag(sync=True)
    submitted_request = traitlets.Dict(default_value={}).tag(sync=True)
    completed_generation = traitlets.Int(0).tag(sync=True)
    completed_elapsed_ms = traitlets.Int(0).tag(sync=True)
    completion_state = traitlets.Unicode("idle").tag(sync=True)
    fixture_llm_override = traitlets.Bool(False).tag(sync=True)

    def __init__(
        self,
        *,
        coordinator: ProviderDiscoveryCoordinator | None = None,
        environ: Mapping[str, str] | None = None,
        engine_availability: Sequence[Mapping[str, object]] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._coordinator = coordinator or ProviderDiscoveryCoordinator()
        runtime_environment = os.environ if environ is None else environ
        self._credential_environment = _safe_environment(runtime_environment)
        self.fixture_llm_override = (
            runtime_environment.get("NXUSKIT_COMMON_SENSE_FIXTURE_LLM") == "1"
        )
        self._engine_availability = list(
            engine_availability
            if engine_availability is not None
            else inspect_reasoning_engine_availability()
        )
        self._snapshots: dict[str, object] = {}
        self.observe(self._handle_scenario, names="scenario")
        self.observe(self._handle_provider, names="selected_provider")
        self.observe(self._handle_refresh, names="refresh_generation")
        self.observe(self._handle_poll, names="poll_generation")
        self._rebuild_modes()
        self._rebuild_engines()
        for provider in LOCAL_PROVIDERS:
            self.apply_discovery_snapshot(self._coordinator.request(provider))

    def _rebuild_engines(self) -> None:
        self.engines = reasoning_engine_options(
            self.scenario, self._engine_availability
        )

    def _rebuild_modes(self) -> None:
        self.modes = scenario_mode_options(self.scenario)

    def _rebuild_providers(self) -> None:
        self.providers = provider_options_for_scenario(
            self.scenario,
            inspect_provider_availability(
                self._credential_environment, self._snapshots
            ),
        )

    def _provider_is_applicable(self, provider_id: object) -> bool:
        return any(
            entry.get("id") == provider_id and entry.get("applicable") is True
            for entry in self.providers
        )

    def _handle_scenario(self, _change: Mapping[str, object]) -> None:
        self._rebuild_modes()
        if self.scenario == "synthetic-claims-audit" and self.mode != "fixture":
            self.mode = "fixture"
        elif self.scenario == "coupon-stack" and self.mode == "live":
            self.mode = "auto"
        self._rebuild_engines()
        self._rebuild_providers()

    def _handle_provider(self, change: Mapping[str, object]) -> None:
        provider = change.get("new")
        if provider and not self._provider_is_applicable(provider):
            return
        self.models = []
        self.selected_model = None
        if not provider:
            self.model_state = "idle"
            self.model_message = "Select a provider to discover models."
            return
        self.apply_discovery_snapshot(
            self._coordinator.request(str(provider), force=False)
        )

    def _handle_refresh(self, change: Mapping[str, object]) -> None:
        if (
            not change.get("new")
            or not self.selected_provider
            or not self._provider_is_applicable(self.selected_provider)
        ):
            return
        self.apply_discovery_snapshot(
            self._coordinator.request(self.selected_provider, force=True)
        )

    def _handle_poll(self, change: Mapping[str, object]) -> None:
        if not change.get("new"):
            return
        providers = list(LOCAL_PROVIDERS)
        if self.selected_provider and self.selected_provider not in providers:
            providers.append(self.selected_provider)
        for provider in providers:
            self.apply_discovery_snapshot(self._coordinator.poll(provider))

    def apply_discovery_snapshot(self, snapshot: object) -> None:
        """Apply safe discovery state without allowing a stale provider UI overwrite."""

        provider = str(getattr(snapshot, "provider", ""))
        if not provider:
            return
        self._snapshots[provider] = snapshot
        self._rebuild_providers()
        local_states = {
            local: getattr(self._snapshots.get(local), "state", "idle")
            for local in LOCAL_PROVIDERS
        }
        self.discovery_loading = not all(
            state in TERMINAL_DISCOVERY_STATES for state in local_states.values()
        )
        if provider != self.selected_provider:
            return
        self.model_state = str(getattr(snapshot, "state", "failed"))
        self.model_message = str(
            getattr(snapshot, "message", "Model discovery was unavailable.")
        )
        rows = [_model_row(model) for model in getattr(snapshot, "models", ())]
        self.models = rows
        available_ids = {str(row["id"]) for row in rows}
        if self.selected_model not in available_ids:
            self.selected_model = None
