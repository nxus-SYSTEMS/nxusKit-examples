"""Promptfoo compatibility importer for common public-safe config shapes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_data


FAIL_CLOSED_KEYS = {
    "javascript": "javascript_assertion",
    "python": "python_assertion",
    "provider_file": "custom_provider_file",
    "redteam": "red_team_plugin",
    "browser": "browser_automation",
}


def import_promptfoo(
    path: Path,
    *,
    allow_code: bool = False,
    native_reference: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    raw = load_data(path)
    blocked = detect_blocked_features(raw, path)
    if blocked and not (allow_code or native_reference):
        return None, {
            "source": str(path),
            "status": "requires_explicit_flag",
            "requires_explicit_flag": True,
            "blocked_features": blocked,
            "accepted_flags": ["--allow-code", "--promptfoo-native-reference"],
        }

    providers = convert_providers(raw.get("providers") or ["mock"])
    prompts = raw.get("prompts") or []
    tests = raw.get("tests") or []
    default_test = raw.get("defaultTest") or {}
    converted_tests = []
    for index, test in enumerate(tests):
        merged = dict(default_test)
        merged.update(test or {})
        prompt_items = prompts or [merged.get("prompt", "")]
        for prompt_index, prompt in enumerate(prompt_items):
            suffix = "" if len(prompt_items) == 1 else f"-prompt-{prompt_index + 1}"
            converted_tests.append(
                {
                    "id": f"{merged.get('id', f'promptfoo-{index + 1}')}{suffix}",
                    "prompt": resolve_prompt(path.parent, prompt),
                    "vars": merged.get("vars") or {},
                    "provider_ids": [provider["id"] for provider in providers],
                    "assertions": convert_assertions(
                        merged.get("assert") or [], allow_code=allow_code
                    ),
                    "mock_response": merged.get("mock_response")
                    or merged.get("expected")
                    or {"label": "billing", "confidence": 0.91, "rationale": "fixture"},
                }
            )

    config = {
        "schema_version": "1.0.0",
        "id": f"promptfoo-import-{path.stem}",
        "description": "Imported Promptfoo config",
        "providers": providers,
        "tests": converted_tests,
        "policy": {"required_fields": ["label", "confidence"]},
        "bayesian": {"prior_alpha": 2, "prior_beta": 2},
    }
    explicit_flag_used = bool(blocked and (allow_code or native_reference))
    status = "converted_with_warnings" if blocked else "converted"
    return config, {
        "source": str(path),
        "status": status,
        "requires_explicit_flag": False,
        "explicit_flag_used": explicit_flag_used,
        "converted_tests": len(converted_tests),
        "converted_providers": len(providers),
        "blocked_features": blocked,
        "execution_note": (
            "Executable or provider-native Promptfoo features were acknowledged by an explicit flag, "
            "JavaScript assertions may execute under --allow-code when node is available; "
            "unsupported or native-reference-only behavior still fails closed unless implemented explicitly."
            if blocked
            else ""
        ),
    }


def detect_blocked_features(raw: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    text = json.dumps(raw).lower()
    blocked = []
    for needle, feature in FAIL_CLOSED_KEYS.items():
        if needle in text:
            blocked.append(
                {
                    "status": "requires_explicit_flag",
                    "feature": feature,
                    "source": str(path),
                    "reason": "imported config contains executable, browser, or provider-specific behavior",
                    "allowed_flags": ["--allow-code", "--promptfoo-native-reference"],
                }
            )
    return blocked


def convert_providers(providers: list[Any]) -> list[dict[str, Any]]:
    out = []
    for index, provider in enumerate(providers):
        if isinstance(provider, str):
            provider_name = provider.split(":", 1)[0]
            out.append(
                {
                    "id": provider_name or f"provider-{index + 1}",
                    "provider": provider_name or "mock",
                    "model": "fixture",
                }
            )
        elif isinstance(provider, dict):
            provider_name = provider.get("provider") or provider.get("id") or "mock"
            out.append(
                {
                    "id": provider.get("id") or provider_name,
                    "provider": provider_name,
                    "label": provider.get("label", provider_name),
                    "model": (provider.get("config") or {}).get("model", "fixture"),
                }
            )
    return out or [{"id": "mock", "provider": "mock", "model": "fixture"}]


def convert_assertions(
    assertions: list[Any], *, allow_code: bool = False
) -> list[dict[str, Any]]:
    converted = []
    for assertion in assertions:
        if isinstance(assertion, str):
            converted.append({"type": assertion})
        elif isinstance(assertion, dict):
            atype = assertion.get("type", "contains")
            item = {"type": atype}
            if "value" in assertion:
                item["value"] = assertion["value"]
            if "pattern" in assertion:
                item["pattern"] = assertion["pattern"]
            if "path" in assertion:
                item["path"] = assertion["path"]
            if atype in {"javascript", "python"}:
                item["allow_code"] = allow_code
            converted.append(item)
    return converted or [{"type": "is-json"}]


def resolve_prompt(base: Path, prompt: Any) -> str:
    if isinstance(prompt, str) and prompt.startswith("file://"):
        rel = prompt.removeprefix("file://")
        return (base / rel).read_text(encoding="utf-8")
    return str(prompt)
