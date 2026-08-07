"""Pure, versioned session export helpers for the Reasoning Lab UI."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PYTHON_ROOT = Path(__file__).resolve().parents[1] / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from llm_interactions import validate_interaction_snapshot  # noqa: E402


KIND = "nxuskit.reasoning-lab-session"
SCHEMA_VERSION = "1.0.0"
TRANSCRIPT_SCHEMA_VERSION = "2.0.0"
SCENARIOS = {
    "car-wash",
    "coupon-stack",
    "pallet-door",
    "cold-chain",
    "synthetic-claims-audit",
}
MODES = {"fixture", "auto", "live"}
ENGINES = {"clips", "bn", "solver", "zen", "claims-audit"}
RESULT_RESPONSE_KEYS = {
    "mode",
    "record",
    "execution",
    "effective_guardrails",
    "skipped_mechanisms",
    "requested_provider",
    "requested_model",
    "message",
}
RUN_RECEIPT_KEYS = {
    "started_at_utc",
    "completed_at_utc",
    "elapsed_ms",
    "status",
}
EVENT_KEYS = {
    "id",
    "sequence",
    "timestamp_utc",
    "category",
    "status",
    "message",
    "attempt",
    "component",
    "llm_interaction_id",
}
EVENT_LINK_KEYS = {"id", "llm_interaction_id"}
EVENT_CATEGORIES = {"run", "provider", "facts", "engine", "repair"}
EVENT_STATUSES = {
    "started",
    "requested",
    "received",
    "completed",
    "accepted",
    "rejected",
    "pass",
    "warn",
    "fail",
    "retry",
    "skipped",
    "stopped",
}
COMPONENT_KEYS = {"kind", "id", "model", "tier"}


def _utc_hundredths(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    hundredths = normalized.microsecond // 10_000
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{hundredths:02d}Z"


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("export value must be JSON-serializable") from exc


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text or null")
    return value


def normalize_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(configuration, Mapping):
        raise ValueError("configuration must be an object")
    scenario = configuration.get("scenario")
    if scenario not in SCENARIOS:
        raise ValueError("configuration scenario is not supported")
    mode = configuration.get("mode")
    if mode not in MODES:
        raise ValueError("configuration mode is not supported")
    provider = _optional_text(configuration.get("provider"), "provider")
    model = _optional_text(configuration.get("model"), "model")
    raw_engines = configuration.get(
        "reasoning_engines", configuration.get("mechanisms", [])
    )
    if isinstance(raw_engines, str) or not isinstance(raw_engines, Sequence):
        raise ValueError("reasoning engines must be a sequence")
    engines = sorted(set(raw_engines))
    if any(not isinstance(item, str) or item not in ENGINES for item in engines):
        raise ValueError("configuration contains an unsupported reasoning engine")
    attempts = configuration.get("max_repair_attempts", 3)
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 1 <= attempts <= 10
    ):
        raise ValueError("max_repair_attempts must be between 1 and 10")
    return {
        "scenario": scenario,
        "mode": mode,
        "provider": provider,
        "model": model,
        "reasoning_engines": engines,
        "max_repair_attempts": attempts,
    }


def configurations_match(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    return normalize_configuration(first) == normalize_configuration(second)


def _safe_response(response: Mapping[str, Any]) -> dict[str, Any]:
    safe = {
        key: _json_copy(response[key])
        for key in RESULT_RESPONSE_KEYS
        if key in response
    }
    record = safe.get("record")
    if record is not None and not isinstance(record, dict):
        raise ValueError("response record must be an object or null")
    return safe


def _safe_receipt(response: Mapping[str, Any]) -> dict[str, Any]:
    raw = response.get("run_receipt")
    if not isinstance(raw, Mapping):
        raise ValueError("result export requires a run receipt")
    receipt = {key: _json_copy(raw[key]) for key in RUN_RECEIPT_KEYS if key in raw}
    if set(receipt) != RUN_RECEIPT_KEYS:
        raise ValueError("run receipt is incomplete")
    if not isinstance(receipt["elapsed_ms"], int) or receipt["elapsed_ms"] < 0:
        raise ValueError("run receipt elapsed_ms must be non-negative")
    if receipt["status"] not in {"completed", "failed", "stopped"}:
        raise ValueError("run receipt status is invalid")
    if not all(
        isinstance(receipt[key], str) for key in ("started_at_utc", "completed_at_utc")
    ):
        raise ValueError("run receipt timestamps must be text")
    return receipt


def _safe_events(
    events: Sequence[Mapping[str, Any]], *, include_links: bool = False
) -> list[dict[str, Any]]:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise ValueError("events must be a sequence")
    safe_events: list[dict[str, Any]] = []
    for expected_sequence, raw in enumerate(events, start=1):
        if not isinstance(raw, Mapping) or not set(raw) <= EVENT_KEYS:
            raise ValueError("event contains non-allowlisted keys")
        if raw.get("sequence") != expected_sequence:
            raise ValueError("event sequence is not contiguous")
        if raw.get("category") not in EVENT_CATEGORIES:
            raise ValueError("event category is invalid")
        if raw.get("status") not in EVENT_STATUSES:
            raise ValueError("event status is invalid")
        message = raw.get("message")
        if (
            not isinstance(message, str)
            or not message
            or len(message) > 240
            or "\n" in message
            or "\r" in message
        ):
            raise ValueError("event message is invalid")
        if not isinstance(raw.get("timestamp_utc"), str):
            raise ValueError("event timestamp is invalid")
        attempt = raw.get("attempt")
        if attempt is not None and (
            not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1
        ):
            raise ValueError("event attempt is invalid")
        component = raw.get("component")
        if component is not None:
            if (
                not isinstance(component, Mapping)
                or not set(component) <= COMPONENT_KEYS
            ):
                raise ValueError("event component is invalid")
            if any(
                not isinstance(value, str) or not value for value in component.values()
            ):
                raise ValueError("event component value is invalid")
        safe = {
            key: _json_copy(value)
            for key, value in raw.items()
            if include_links or key not in EVENT_LINK_KEYS
        }
        if include_links:
            if raw.get("id") != f"event-{expected_sequence:04d}":
                raise ValueError("event ID is not contiguous")
            interaction_id = raw.get("llm_interaction_id")
            if interaction_id is not None and not (
                isinstance(interaction_id, str)
                and len(interaction_id) == 8
                and interaction_id.startswith("llm-")
                and interaction_id[4:].isdigit()
            ):
                raise ValueError("event interaction ID is invalid")
        safe_events.append(safe)
    return safe_events


def _safe_interactions(
    interactions: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(interactions, (str, bytes)) or not isinstance(interactions, Sequence):
        raise ValueError("LLM interactions must be a sequence")
    safe_interactions = []
    for expected_sequence, raw in enumerate(interactions, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError("LLM interaction must be an object")
        if raw.get("id") != f"llm-{expected_sequence:04d}":
            raise ValueError("LLM interaction IDs must be contiguous")
        safe_interactions.append(validate_interaction_snapshot(raw))

    events_by_id = {event["id"]: event for event in events}
    interactions_by_id = {
        interaction["id"]: interaction for interaction in safe_interactions
    }
    for interaction in safe_interactions:
        for event_id in interaction["linked_event_ids"]:
            event = events_by_id.get(event_id)
            if event is None:
                raise ValueError("LLM interaction links an unknown event")
            if event.get("llm_interaction_id") != interaction["id"]:
                raise ValueError("LLM interaction and event links do not match")
    for event in events:
        interaction_id = event.get("llm_interaction_id")
        if interaction_id is None:
            continue
        interaction = interactions_by_id.get(interaction_id)
        if interaction is None or event["id"] not in interaction["linked_event_ids"]:
            raise ValueError("event links an unknown LLM interaction")
    return _json_copy(safe_interactions)


def build_session_document(
    configuration: Mapping[str, Any],
    *,
    response: Mapping[str, Any] | None = None,
    events: Sequence[Mapping[str, Any]] = (),
    llm_interactions: Sequence[Mapping[str, Any]] = (),
    include_full_transcript: bool = False,
    exported_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = exported_at or datetime.now(timezone.utc)
    if not isinstance(include_full_transcript, bool):
        raise ValueError("transcript option must be boolean")
    if include_full_transcript and response is None:
        raise ValueError("full transcript export requires a results-bearing session")
    results = None
    if response is not None:
        if not isinstance(response, Mapping):
            raise ValueError("response must be an object")
        safe_events = _safe_events(events, include_links=include_full_transcript)
        results = {
            "response": _safe_response(response),
            "run_receipt": _safe_receipt(response),
            "events": safe_events,
        }
        if include_full_transcript:
            results["llm_interactions"] = _safe_interactions(
                llm_interactions, safe_events
            )
    elif events:
        raise ValueError("settings-only exports cannot contain events")
    return {
        "kind": KIND,
        "schema_version": (
            TRANSCRIPT_SCHEMA_VERSION if include_full_transcript else SCHEMA_VERSION
        ),
        "exported_at_utc": _utc_hundredths(timestamp),
        "configuration": normalize_configuration(configuration),
        "results": results,
    }


def serialize_session_document(document: Mapping[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def export_filename(scenario: str, exported_at: datetime) -> str:
    if scenario not in SCENARIOS:
        raise ValueError("export scenario is not supported")
    if exported_at.tzinfo is None or exported_at.utcoffset() is None:
        raise ValueError("export timestamp must be timezone-aware")
    normalized = exported_at.astimezone(timezone.utc)
    return f"reasoning-lab-{scenario}-{normalized:%Y%m%dT%H%M%SZ}.json"
