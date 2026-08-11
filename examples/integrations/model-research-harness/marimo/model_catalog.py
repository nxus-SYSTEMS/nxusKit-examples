"""Safe, read-only Model Research provider discovery through nxusKit CLI v1.0.5."""

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


def _run(command: list[str], runner: Runner) -> subprocess.CompletedProcess[str]:
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


def _descriptions(payload: Mapping[str, object]) -> dict[str, str]:
    result = payload.get("result")
    models = result.get("models") if isinstance(result, Mapping) else None
    if not isinstance(models, list):
        return {}
    return {
        str(item["id"]): str(item["name"]).strip()
        for item in models
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and item.get("id")
        and isinstance(item.get("name"), str)
        and str(item["name"]).strip()
    }


def _models(
    provider: str,
    payload: Mapping[str, object],
    descriptions: Mapping[str, str],
) -> tuple[CatalogModel, ...] | None:
    result = payload.get("result")
    raw_models = result.get("models") if isinstance(result, Mapping) else None
    if not isinstance(raw_models, list):
        return None
    models: list[CatalogModel] = []
    for item in raw_models:
        if not isinstance(item, Mapping):
            return None
        model_id = item.get("id")
        model_provider = item.get("provider")
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or model_provider != provider
        ):
            return None
        raw_name = item.get("name")
        raw_supports = item.get("supports")
        raw_context = item.get("context_window")
        models.append(
            CatalogModel(
                id=model_id,
                name=(
                    raw_name.strip()
                    if isinstance(raw_name, str) and raw_name.strip()
                    else model_id
                ),
                provider=provider,
                supports=(
                    tuple(
                        value
                        for value in raw_supports
                        if isinstance(value, str) and value in MODEL_CAPABILITIES
                    )
                    if isinstance(raw_supports, list)
                    else ()
                ),
                context_window=(
                    raw_context
                    if isinstance(raw_context, int)
                    and not isinstance(raw_context, bool)
                    and raw_context > 0
                    else None
                ),
                local=item.get("local") is True,
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
    """Return a safe model catalog without inference or provider mutation."""

    if provider not in PROVIDERS:
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    cli = _cli(environ)
    models_command = [cli, "models", "--provider", provider, "--format", "json"]
    if provider in LOCAL_PROVIDERS:
        models_command.append("--local-only")
    try:
        models_payload = _payload(_run(models_command, runner))
        info_payload = _payload(
            _run([cli, "provider", "info", provider, "--json"], runner)
        )
    except subprocess.TimeoutExpired:
        return CatalogResult(provider, "failed", (), "Model discovery timed out.")
    except (OSError, subprocess.SubprocessError):
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    if models_payload is None or info_payload is None:
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    models = _models(provider, models_payload, _descriptions(info_payload))
    if models is None:
        return CatalogResult(provider, "failed", (), "Model discovery was unavailable.")
    if not models:
        return CatalogResult(provider, "empty", (), "No models were reported.")
    return CatalogResult(provider, "ready", models, "Models ready.")
