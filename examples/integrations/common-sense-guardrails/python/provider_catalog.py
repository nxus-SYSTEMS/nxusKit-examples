"""Safe, read-only provider discovery through released nxusKit CLI v1.0.5."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal


DISCOVERY_COMMAND_TIMEOUT_SECONDS = 6
PROVIDERS = {"claude", "openai", "groq", "xai", "ollama", "lmstudio"}
LOCAL_PROVIDERS = {"ollama", "lmstudio"}
MODEL_CAPABILITIES = {"chat", "streaming", "vision", "function_calling"}
Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CatalogModel:
    id: str
    name: str
    provider: str
    supports: tuple[str, ...]
    context_window: int | None
    local: bool
    description: str | None


@dataclass(frozen=True)
class CatalogResult:
    provider: str
    state: Literal["ready", "empty", "failed"]
    models: tuple[CatalogModel, ...]
    message: str


def _cli(environ: Mapping[str, str] | None) -> str:
    environment = os.environ if environ is None else environ
    return environment.get("NXUSKIT_CLI", "nxuskit-cli")


def _run(command: list[str], runner: Runner) -> subprocess.CompletedProcess[str] | None:
    return runner(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=DISCOVERY_COMMAND_TIMEOUT_SECONDS,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> Mapping[str, object] | None:
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, Mapping) else None


def _model_description_by_id(payload: Mapping[str, object]) -> dict[str, str]:
    result = payload.get("result")
    models = result.get("models") if isinstance(result, Mapping) else None
    if not isinstance(models, list):
        return {}
    descriptions: dict[str, str] = {}
    for model in models:
        if not isinstance(model, Mapping):
            continue
        model_id = model.get("id")
        description = model.get("name")
        if (
            isinstance(model_id, str)
            and model_id
            and isinstance(description, str)
            and description.strip()
        ):
            descriptions[model_id] = description.strip()
    return descriptions


def _catalog_models(
    provider: str,
    payload: Mapping[str, object],
    descriptions: Mapping[str, str],
) -> tuple[CatalogModel, ...] | None:
    result = payload.get("result")
    raw_models = result.get("models") if isinstance(result, Mapping) else None
    if not isinstance(raw_models, list):
        return None
    models: list[CatalogModel] = []
    for raw_model in raw_models:
        if not isinstance(raw_model, Mapping):
            return None
        model_id = raw_model.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            return None
        model_provider = raw_model.get("provider")
        if not isinstance(model_provider, str) or model_provider != provider:
            return None
        raw_name = raw_model.get("name")
        name = (
            raw_name.strip()
            if isinstance(raw_name, str) and raw_name.strip()
            else model_id
        )
        raw_supports = raw_model.get("supports")
        supports = (
            tuple(
                capability
                for capability in raw_supports
                if isinstance(capability, str) and capability in MODEL_CAPABILITIES
            )
            if isinstance(raw_supports, list)
            else ()
        )
        raw_context = raw_model.get("context_window")
        context_window = (
            raw_context
            if isinstance(raw_context, int)
            and not isinstance(raw_context, bool)
            and raw_context > 0
            else None
        )
        models.append(
            CatalogModel(
                id=model_id,
                name=name,
                provider=model_provider,
                supports=supports,
                context_window=context_window,
                local=raw_model.get("local") is True,
                description=descriptions.get(model_id),
            )
        )
    return tuple(models)


def discover_provider_models(
    provider: str,
    *,
    runner: Runner = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> CatalogResult:
    """Return a safe model catalog without inference or provider lifecycle effects."""

    if provider not in PROVIDERS:
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    cli = _cli(environ)
    models_command = [cli, "models", "--provider", provider, "--format", "json"]
    if provider in LOCAL_PROVIDERS:
        models_command.append("--local-only")
    info_command = [cli, "provider", "info", provider, "--json"]
    try:
        models_result = _run(models_command, runner)
        info_result = _run(info_command, runner)
    except subprocess.TimeoutExpired:
        return CatalogResult(provider, "failed", (), "Model discovery timed out.")
    except (OSError, subprocess.SubprocessError):
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    models_payload = _payload(models_result)
    info_payload = _payload(info_result)
    if models_payload is None or info_payload is None:
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    models = _catalog_models(
        provider, models_payload, _model_description_by_id(info_payload)
    )
    if models is None:
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    if not models:
        return CatalogResult(provider, "empty", (), "No models were reported.")
    return CatalogResult(provider, "ready", models, "Models ready.")


def provider_reachable(
    provider: str,
    *,
    runner: Runner = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return the released CLI's bounded, non-mutating provider reachability result."""

    if provider not in PROVIDERS:
        return False
    command = [
        _cli(environ),
        "provider",
        "ping",
        "--provider",
        provider,
        "--json",
        "--timeout",
        "750",
    ]
    try:
        result = _run(command, runner)
    except (OSError, subprocess.SubprocessError):
        return False
    payload = _payload(result)
    return payload is not None and payload.get("reachable") is True
