"""Deterministic policy checks modeled as CLIPS-style findings."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


def evaluate_policy(
    result: dict[str, Any],
    policy: dict[str, Any] | None,
    *,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    if not policy:
        return {
            "engine": "clips",
            "status": "pass",
            "findings": [],
            "disposition": "allow",
        }
    if policy.get("engine") == "nxuskit-clips":
        return evaluate_with_nxuskit_clips(result, policy, config_dir)

    return evaluate_python_policy(result, policy)


def evaluate_python_policy(
    result: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    parsed = result.get("parsed_output")
    findings: list[dict[str, Any]] = []

    for field in policy.get("required_fields", []):
        if not isinstance(parsed, dict) or field not in parsed:
            findings.append(
                {
                    "rule_id": f"required-field-{field}",
                    "severity": "high",
                    "message": f"Missing required field: {field}",
                }
            )

    for rule in policy.get("forbidden_values", []):
        field = rule.get("field")
        forbidden = set(rule.get("values") or [])
        if isinstance(parsed, dict) and parsed.get(field) in forbidden:
            findings.append(
                {
                    "rule_id": rule.get("id", f"forbidden-{field}"),
                    "severity": rule.get("severity", "medium"),
                    "message": f"{field} used forbidden value {parsed.get(field)!r}",
                }
            )

    for rule in policy.get("protected_paths", []):
        touched = set(result.get("metadata", {}).get("touched_paths") or [])
        protected = set(rule.get("paths") or [])
        overlap = sorted(touched & protected)
        if overlap:
            findings.append(
                {
                    "rule_id": rule.get("id", "protected-path"),
                    "severity": "high",
                    "message": f"Patch touched protected paths: {', '.join(overlap)}",
                }
            )

    disposition = "block" if any(f["severity"] == "high" for f in findings) else "allow"
    return {
        "engine": "python-clips-style",
        "status": "pass" if not findings else "fail",
        "findings": findings,
        "disposition": disposition,
    }


def evaluate_with_nxuskit_clips(
    result: dict[str, Any],
    policy: dict[str, Any],
    config_dir: Path | None,
) -> dict[str, Any]:
    try:
        from nxuskit import ClipsSession
    except Exception as exc:  # noqa: BLE001
        return handle_engine_unavailable(result, policy, f"{type(exc).__name__}: {exc}")

    clips_cfg = policy.get("clips") or {}
    rules_file = resolve_path(clips_cfg.get("rules_file"), config_dir)
    if not rules_file:
        return handle_engine_unavailable(
            result, policy, "nxuskit-clips policy requires clips.rules_file"
        )

    fact_template = clips_cfg.get("fact_template", "model-output")
    finding_template = clips_cfg.get("finding_template", "policy-finding")
    slot_map = clips_cfg.get("slot_map") or {
        "label": "label",
        "confidence": "confidence",
    }
    parsed = result.get("parsed_output")
    if not isinstance(parsed, dict):
        parsed = {}

    try:
        with ClipsSession() as clips:
            clips.load_file(str(rules_file))
            clips.reset()
            clips.fact_assert_string(make_fact(fact_template, slot_map, parsed))
            fired = clips.run(int(clips_cfg.get("run_limit", -1)))
            findings = []
            for fact_index in clips.facts_by_template(finding_template):
                slots = clips.fact_slot_values(fact_index)
                if isinstance(slots, str):
                    slots = json.loads(slots)
                findings.append(normalize_finding_slots(slots))
    except Exception as exc:  # noqa: BLE001
        return handle_engine_unavailable(result, policy, f"{type(exc).__name__}: {exc}")

    disposition = (
        "block" if any(item.get("severity") == "high" for item in findings) else "allow"
    )
    return {
        "engine": "nxuskit-clips",
        "status": "pass" if not findings else "fail",
        "findings": findings,
        "disposition": disposition,
        "rules_fired": fired,
        "rules_file": str(rules_file),
    }


def handle_engine_unavailable(
    result: dict[str, Any], policy: dict[str, Any], reason: str
) -> dict[str, Any]:
    behavior = policy.get("on_engine_unavailable", "fallback-python")
    if behavior == "fallback-python":
        fallback = evaluate_python_policy(result, policy)
        fallback["engine"] = "python-clips-style-fallback"
        fallback["engine_unavailable"] = reason
        return fallback
    return {
        "engine": "nxuskit-clips",
        "status": "fail",
        "findings": [
            {
                "rule_id": "clips-engine-unavailable",
                "severity": "high",
                "message": reason,
            }
        ],
        "disposition": "block",
        "engine_unavailable": reason,
    }


def resolve_path(value: Any, config_dir: Path | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    base = config_dir or Path.cwd()
    return (base / path).resolve()


def make_fact(template: str, slot_map: dict[str, str], parsed: dict[str, Any]) -> str:
    slots = []
    for slot_name, field_name in slot_map.items():
        slots.append(f"({slot_name} {to_clips_value(parsed.get(field_name))})")
    return f"({template} {' '.join(slots)})"


def to_clips_value(value: Any) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unwrap_clips_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "value" in value:
            return value["value"]
        if "String" in value:
            return value["String"]
        if "Symbol" in value:
            return value["Symbol"]
        if "Integer" in value:
            return value["Integer"]
        if "Float" in value:
            return value["Float"]
    return value


def normalize_finding_slots(slots: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": str(
            unwrap_clips_value(
                slots.get("rule-id", slots.get("rule_id", "clips-finding"))
            )
        ),
        "severity": str(unwrap_clips_value(slots.get("severity", "medium"))),
        "message": str(unwrap_clips_value(slots.get("message", ""))),
    }
