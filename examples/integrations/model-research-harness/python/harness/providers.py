"""Provider adapters used by the model research harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import base64
import urllib.error
import urllib.request
from typing import Any

from .activity import EvaluationTrace
from .templating import render_template


class ProviderError(RuntimeError):
    """Raised when live provider execution cannot run."""


def capability_truth(
    provider: dict[str, Any], observed: dict[str, Any] | None = None
) -> dict[str, Any]:
    caps = provider.get("capabilities") or {}
    observed = observed or {}
    return {
        "provider_id": provider["id"],
        "provider": provider.get("provider"),
        "model": provider.get("model", ""),
        "native_strict_schema": bool(caps.get("native_strict_schema", False)),
        "json_mode": bool(caps.get("json_mode", False)),
        "harness_validated": bool(observed.get("harness_validated", True)),
        "harness_repaired": bool(observed.get("harness_repaired", False)),
        "thinking_control": caps.get("thinking_control", "unavailable"),
        "tool_calling": caps.get("tool_calling", "unavailable"),
    }


def call_provider(
    provider: dict[str, Any],
    test: dict[str, Any],
    mode: str,
    provider_override: str | None = None,
    model_override: str | None = None,
    trace: EvaluationTrace | None = None,
) -> dict[str, Any]:
    prompt = render_template(test["prompt"], test.get("vars") or {})
    fixture_response = mode == "mock" or (
        not provider_override and provider.get("provider") in {"mock", "loopback"}
    )
    if mode == "auto" and not live_provider_available(
        provider_override or provider.get("provider")
    ):
        fixture_response = True

    interaction_id: str | None = None
    if trace is not None:
        interaction_id = trace.begin_interaction(
            test_id=str(test["id"]),
            source="mock" if fixture_response else "live",
            provider=str(
                provider_override or provider.get("provider") or provider.get("id", "")
            ),
            model=str(model_override or provider.get("model", "")),
            system_prompt=(
                None
                if not (test.get("system_prompt") or provider.get("system_prompt"))
                else str(test.get("system_prompt") or provider.get("system_prompt"))
            ),
            user_prompt=prompt,
        )

    try:
        if fixture_response:
            response = _mock_response(provider, test)
        else:
            response = call_live_provider(
                provider, test, prompt, provider_override, model_override
            )
    except Exception as exc:
        if trace is not None and interaction_id is not None:
            trace.fail_interaction(interaction_id, error_message=str(exc))
        raise

    if trace is not None and interaction_id is not None:
        trace.receive_interaction(
            interaction_id, response_content=str(response.get("content", ""))
        )
        response["_trace_interaction_id"] = interaction_id
    return response


def _mock_response(provider: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    """Build the existing deterministic fixture response."""

    mock = test.get("mock_response", {})
    if isinstance(mock, dict):
        content = json.dumps(mock, sort_keys=True)
    else:
        content = str(mock)
    return {
        "content": content,
        "source": "mock",
        "model": provider.get("model", "fixture"),
        "latency_ms": 0,
        "metadata": test.get("metadata") or {},
    }


def live_provider_available(provider_name: str | None) -> bool:
    if provider_name in {"ollama", "lmstudio"}:
        return True
    env_map = {
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "xai": "XAI_API_KEY",
    }
    return bool(provider_name and os.environ.get(env_map.get(provider_name, "")))


def call_live_provider(
    provider: dict[str, Any],
    test: dict[str, Any],
    prompt: str,
    provider_override: str | None,
    model_override: str | None,
) -> dict[str, Any]:
    provider_name = provider_override or provider.get("provider")
    model = model_override or provider.get("model")
    if provider_name == "ollama" and (
        provider.get("native_ollama") or test.get("native_ollama")
    ):
        return call_native_ollama(provider, test, prompt, model)

    try:
        from nxuskit import Message, Provider, ResponseFormat
    except ImportError as exc:
        raise ProviderError("live mode requires nxuskit-py on PYTHONPATH") from exc

    if provider_name == "claude":
        client = Provider.claude(
            model=model, api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
    elif provider_name == "openai":
        client = Provider.openai(model=model, api_key=os.environ.get("OPENAI_API_KEY"))
    elif provider_name == "groq":
        client = Provider.groq(model=model, api_key=os.environ.get("GROQ_API_KEY"))
    elif provider_name == "xai":
        client = Provider.xai(model=model, api_key=os.environ.get("XAI_API_KEY"))
    elif provider_name == "ollama":
        client = Provider.ollama(model=model)
    elif provider_name == "lmstudio":
        client = Provider.lmstudio(model=model)
    else:
        raise ProviderError(
            f"unsupported live provider {provider_name!r}; supported: claude, openai, groq, xai, ollama, lmstudio"
        )

    messages = []
    if provider.get("system_prompt") or test.get("system_prompt"):
        messages.append(
            Message.system(
                str(test.get("system_prompt") or provider.get("system_prompt"))
            )
        )
    user_message = Message.user(prompt)
    for image in test.get("images") or []:
        image_text = render_template(str(image), test.get("vars") or {})
        user_message.with_image_file(image_text)
    messages.append(user_message)

    response_format = ResponseFormat.TEXT
    if (
        test.get("response_format") or provider.get("response_format") or "json"
    ) == "json":
        response_format = ResponseFormat.JSON

    response = client.chat(
        messages,
        temperature=float(provider.get("temperature", 0.1)),
        max_tokens=int(provider.get("max_tokens", 512)),
        response_format=response_format,
    )
    return {
        "content": response.content,
        "source": "live",
        "provider_id": provider_name,
        "model": getattr(response, "model", model),
        "latency_ms": 0,
        "metadata": {
            "images": test.get("images") or [],
            "response_format": response_format.value,
        },
    }


def call_native_ollama(
    provider: dict[str, Any],
    test: dict[str, Any],
    prompt: str,
    model: str,
) -> dict[str, Any]:
    """Use Ollama's native API for knobs not yet normalized by every provider."""

    host = str(
        provider.get("api_url")
        or os.environ.get("OLLAMA_HOST")
        or "http://localhost:11434"
    ).rstrip("/")
    messages = []
    if provider.get("system_prompt") or test.get("system_prompt"):
        messages.append(
            {
                "role": "system",
                "content": str(
                    test.get("system_prompt") or provider.get("system_prompt")
                ),
            }
        )
    user_message: dict[str, Any] = {"role": "user", "content": prompt}
    images = []
    for image in test.get("images") or []:
        image_path = Path(
            render_template(str(image), test.get("vars") or {})
        ).expanduser()
        images.append(base64.b64encode(image_path.read_bytes()).decode("utf-8"))
    if images:
        user_message["images"] = images
    messages.append(user_message)

    options = dict(provider.get("options") or {})
    if "temperature" in provider:
        options.setdefault("temperature", float(provider["temperature"]))
    if "max_tokens" in provider:
        options.setdefault("num_predict", int(provider["max_tokens"]))
    if "num_predict" in provider:
        options.setdefault("num_predict", int(provider["num_predict"]))

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
    }
    schema = test.get("schema") or provider.get("schema")
    response_format = (
        test.get("response_format") or provider.get("response_format") or "json"
    )
    if schema:
        payload["format"] = schema
    elif response_format == "json":
        payload["format"] = "json"
    think = test.get("think", provider.get("think"))
    if think is not None:
        payload["think"] = think
    if test.get("tools") or provider.get("tools"):
        payload["tools"] = test.get("tools") or provider.get("tools")

    request = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(provider.get("timeout", 120))
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if "think" not in payload:
            raise ProviderError(
                f"Ollama HTTP {exc.code}: {exc.read().decode('utf-8')[:500]}"
            ) from exc
        payload.pop("think", None)
        retry = urllib.request.Request(
            f"{host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            retry, timeout=float(provider.get("timeout", 120))
        ) as response:
            data = json.loads(response.read().decode("utf-8"))

    message = data.get("message") or {}
    return {
        "content": message.get("content", ""),
        "source": "live-native-ollama",
        "model": data.get("model", model),
        "latency_ms": 0,
        "metadata": {
            "images": len(images),
            "native_ollama": True,
            "think": payload.get("think"),
            "format": payload.get("format"),
            "tool_calls": message.get("tool_calls") or [],
        },
    }
