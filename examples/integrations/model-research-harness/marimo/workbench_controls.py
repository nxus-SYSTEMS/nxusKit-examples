"""AnyWidget bridge for the Model Research Workbench configuration surface."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import anywidget
import traitlets

from availability import CLOUD_PROVIDERS, inspect_engine_availability
from config_catalog import build_config_catalog
from model_discovery import ProviderDiscoveryCoordinator


ROOT = Path(__file__).resolve().parents[1]
LOCAL_PROVIDERS = ("ollama", "lmstudio")
TERMINAL_DISCOVERY_STATES = {"ready", "empty", "stale", "failed"}
MODES = (
    {
        "id": "mock",
        "label": "Fixture",
        "message": "Deterministic synthetic evidence; no provider call.",
    },
    {
        "id": "auto",
        "label": "Auto",
        "message": "Use a selected compatible provider when available, with only supported fallback.",
    },
    {
        "id": "live",
        "label": "Live",
        "message": "Run the selected available provider and model.",
    },
    {
        "id": "dry-run-policy",
        "label": "Policy Dry Run",
        "message": "Evaluate fixture evidence without provider or lifecycle effects.",
    },
    {
        "id": "import-promptfoo",
        "label": "Promptfoo Import",
        "message": "Inspect supported Promptfoo input only after explicit submission.",
    },
)


def _safe_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """Retain credential names only; never synchronize their values."""

    return {
        credential: "detected"
        for _provider, credential in CLOUD_PROVIDERS
        if credential in environ
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


class WorkbenchControls(anywidget.AnyWidget):
    """Present draft configuration and emit immutable explicit-run snapshots."""

    _esm = Path(__file__).with_name("workbench_controls.js")
    _css = Path(__file__).with_name("workbench_controls.css")

    configs = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
    selected_config = traitlets.Unicode("nxuskit-harness-basic.yaml").tag(sync=True)
    modes = traitlets.List(trait=traitlets.Dict()).tag(sync=True)
    selected_mode = traitlets.Unicode("mock").tag(sync=True)
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
    include_tests = traitlets.Unicode("").tag(sync=True)
    exclude_tests = traitlets.Unicode("").tag(sync=True)
    allow_external = traitlets.Bool(False).tag(sync=True)
    write_reports = traitlets.Bool(False).tag(sync=True)
    refresh_generation = traitlets.Int(0).tag(sync=True)
    poll_generation = traitlets.Int(0).tag(sync=True)
    submit_generation = traitlets.Int(0).tag(sync=True)
    submitted_request = traitlets.Dict(default_value={}).tag(sync=True)
    completed_generation = traitlets.Int(0).tag(sync=True)
    completion_state = traitlets.Unicode("idle").tag(sync=True)

    def __init__(
        self,
        *,
        coordinator: ProviderDiscoveryCoordinator | None = None,
        environ: Mapping[str, str] | None = None,
        license_status: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        runtime_environment = os.environ if environ is None else environ
        self._credential_environment = _safe_environment(runtime_environment)
        self._coordinator = coordinator or ProviderDiscoveryCoordinator()
        self._snapshots: dict[str, object] = {}
        self.configs = build_config_catalog(ROOT)
        self.modes = [dict(mode) for mode in MODES]
        self.engines = inspect_engine_availability(license_status=license_status)
        self._rebuild_providers()
        self.observe(self._handle_provider, names="selected_provider")
        self.observe(self._handle_refresh, names="refresh_generation")
        self.observe(self._handle_poll, names="poll_generation")
        for provider in LOCAL_PROVIDERS:
            self.apply_discovery_snapshot(self._coordinator.request(provider))

    def _rebuild_providers(self) -> None:
        providers: list[dict[str, object]] = []
        credential_names = dict(CLOUD_PROVIDERS)
        for provider in ("claude", "openai", "groq", "xai"):
            credential = credential_names[provider]
            enabled = credential in self._credential_environment
            providers.append(
                {
                    "id": provider,
                    "enabled": enabled,
                    "visible": True,
                    "status": "available" if enabled else "credential_not_detected",
                    "reason": (
                        "Credential name detected; execution still requires explicit Run."
                        if enabled
                        else f"{credential} is not detected."
                    ),
                }
            )
        for provider in LOCAL_PROVIDERS:
            state = str(getattr(self._snapshots.get(provider), "state", "idle"))
            enabled = state in {"ready", "empty", "stale"}
            providers.append(
                {
                    "id": provider,
                    "enabled": enabled,
                    "visible": True,
                    "status": "available" if enabled else state,
                    "reason": (
                        "Released nxusKit model discovery reached the local provider."
                        if enabled
                        else "Waiting for bounded released nxusKit model discovery."
                    ),
                }
            )
        self.providers = providers

    def _handle_provider(self, change: Mapping[str, object]) -> None:
        provider = change.get("new")
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
        if change.get("new") and self.selected_provider:
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
        provider = str(getattr(snapshot, "provider", ""))
        if not provider:
            return
        self._snapshots[provider] = snapshot
        self._rebuild_providers()
        local_states = {
            local: str(getattr(self._snapshots.get(local), "state", "idle"))
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
        if self.selected_model not in {str(row["id"]) for row in rows}:
            self.selected_model = None
