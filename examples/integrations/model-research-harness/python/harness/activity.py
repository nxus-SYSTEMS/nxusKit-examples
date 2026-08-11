"""Dependency-free, allowlisted activity projection for Model Research runs."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any


EVENT_STATUSES = {
    "started",
    "requested",
    "received",
    "parsed",
    "completed",
    "accepted",
    "rejected",
    "failed",
    "error",
    "unsupported",
    "skipped",
}
INTERACTION_STATUSES = {"requested", "received", "evaluated", "error"}
FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "headers",
    "environment",
    "license_token",
    "credential",
}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("trace values must be JSON-compatible") from exc


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).casefold() in FORBIDDEN_KEYS:
                raise ValueError(f"forbidden trace field: {key}")
            _reject_forbidden_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_keys(nested)


def _reject_extra_fields(fields: Mapping[str, Any]) -> None:
    _reject_forbidden_keys(fields)
    if fields:
        names = ", ".join(sorted(fields))
        raise ValueError(f"unsupported trace field: {names}")


class EvaluationTrace:
    """Project canonical runner boundaries into safe incremental UI snapshots."""

    def __init__(
        self,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        interaction_sink: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._event_sink = event_sink
        self._interaction_sink = interaction_sink
        self._clock = clock or _utc_now
        self._event_sequence = 0
        self._interaction_sequence = 0
        self._interactions: dict[str, dict[str, Any]] = {}

    def event(
        self,
        *,
        phase: str,
        status: str,
        summary: str,
        interaction_id: str | None = None,
        test_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        details: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> str:
        """Emit one allowlisted event with a trace-owned contiguous identifier."""

        _reject_extra_fields(fields)
        if status not in EVENT_STATUSES:
            raise ValueError(f"unsupported event status: {status}")
        if not str(phase).strip():
            raise ValueError("event phase must be non-empty")
        if not str(summary).strip():
            raise ValueError("event summary must be non-empty")
        if interaction_id is not None:
            self._require_interaction(interaction_id)

        projected_details = dict(details or {})
        _reject_forbidden_keys(projected_details)
        self._event_sequence += 1
        event_id = f"event-{self._event_sequence:04d}"
        record: dict[str, Any] = {
            "id": event_id,
            "timestamp": str(self._clock()),
            "phase": str(phase),
            "status": status,
            "summary": str(summary),
        }
        for key, value in (
            ("interaction_id", interaction_id),
            ("test_id", test_id),
            ("provider", provider),
            ("model", model),
        ):
            if value is not None:
                record[key] = str(value)
        if projected_details:
            record["details"] = projected_details
        _reject_forbidden_keys(record)

        if interaction_id is not None:
            self._interactions[interaction_id]["linked_event_ids"].append(event_id)
        if self._event_sink is not None:
            self._event_sink(_json_copy(record))
        return event_id

    def begin_interaction(
        self,
        *,
        test_id: str,
        source: str,
        provider: str,
        model: str,
        system_prompt: str | None,
        user_prompt: str,
        **fields: Any,
    ) -> str:
        """Create one requested interaction immediately before provider work."""

        _reject_extra_fields(fields)
        self._interaction_sequence += 1
        interaction_id = f"interaction-{self._interaction_sequence:04d}"
        provenance_label = (
            "Fixture Response — No Provider Contacted"
            if source in {"fixture", "mock"}
            else "Live Provider Response"
        )
        interaction: dict[str, Any] = {
            "id": interaction_id,
            "timestamp": str(self._clock()),
            "test_id": str(test_id),
            "source": str(source),
            "provenance_label": provenance_label,
            "provider": str(provider),
            "model": str(model),
            "system_prompt": None if system_prompt is None else str(system_prompt),
            "user_prompt": str(user_prompt),
            "status": "requested",
            "linked_event_ids": [],
        }
        _reject_forbidden_keys(interaction)
        self._interactions[interaction_id] = interaction
        self.event(
            phase="model_request",
            status="requested",
            summary=f"Requested model interaction for {test_id}.",
            interaction_id=interaction_id,
            test_id=str(test_id),
            provider=str(provider),
            model=str(model),
        )
        self._emit_interaction(interaction_id)
        return interaction_id

    def receive_interaction(
        self,
        interaction_id: str,
        *,
        response_content: str,
        **fields: Any,
    ) -> None:
        """Attach the complete response text to an existing interaction."""

        _reject_extra_fields(fields)
        interaction = self._require_interaction(interaction_id)
        self.event(
            phase="model_response",
            status="received",
            summary=f"Received model response for {interaction['test_id']}.",
            interaction_id=interaction_id,
            test_id=str(interaction["test_id"]),
            provider=str(interaction["provider"]),
            model=str(interaction["model"]),
        )
        interaction["status"] = "received"
        interaction["response"] = str(response_content)
        self._emit_interaction(interaction_id)

    def fail_interaction(
        self,
        interaction_id: str,
        *,
        error_message: str,
        **fields: Any,
    ) -> None:
        """End a requested interaction with a fixed, non-secret error."""

        _reject_extra_fields(fields)
        interaction = self._require_interaction(interaction_id)
        _ = error_message
        self.event(
            phase="model_response",
            status="error",
            summary=f"Model interaction failed for {interaction['test_id']}.",
            interaction_id=interaction_id,
            test_id=str(interaction["test_id"]),
            provider=str(interaction["provider"]),
            model=str(interaction["model"]),
        )
        interaction["status"] = "error"
        interaction["error"] = "Provider interaction failed."
        self._emit_interaction(interaction_id)

    def evaluate_interaction(
        self,
        interaction_id: str,
        *,
        parsed: Any,
        parse_error: str | None,
        assertions: list[dict[str, Any]],
        policy: Mapping[str, Any],
        **fields: Any,
    ) -> None:
        """Project canonical parse, assertion, and policy results without rescoring."""

        _reject_extra_fields(fields)
        interaction = self._require_interaction(interaction_id)
        _reject_forbidden_keys(parsed)
        _reject_forbidden_keys(assertions)
        _reject_forbidden_keys(policy)

        self.event(
            phase="parse",
            status="parsed" if parse_error is None else "error",
            summary=(
                f"Parsed model response for {interaction['test_id']}."
                if parse_error is None
                else f"Could not parse model response for {interaction['test_id']}."
            ),
            interaction_id=interaction_id,
            test_id=str(interaction["test_id"]),
        )
        for assertion in assertions:
            assertion_status = str(assertion.get("status", "unsupported"))
            event_status = {
                "pass": "accepted",
                "fail": "rejected",
                "unsupported": "unsupported",
            }.get(assertion_status, "error")
            self.event(
                phase="assertion",
                status=event_status,
                summary=(
                    f"Assertion {assertion.get('type', 'unknown')} "
                    f"{assertion_status} for {interaction['test_id']}."
                ),
                interaction_id=interaction_id,
                test_id=str(interaction["test_id"]),
                details={
                    key: assertion[key]
                    for key in ("type", "status", "detail", "weight")
                    if key in assertion
                },
            )
        policy_status = str(policy.get("status", "skipped"))
        self.event(
            phase="policy",
            status={"pass": "accepted", "fail": "rejected"}.get(
                policy_status, "skipped"
            ),
            summary=f"Policy evaluation {policy_status} for {interaction['test_id']}.",
            interaction_id=interaction_id,
            test_id=str(interaction["test_id"]),
        )

        interaction["status"] = "evaluated"
        interaction["parsed"] = _json_copy(parsed) if parse_error is None else None
        interaction["parse_error"] = (
            None if parse_error is None else "Response could not be parsed as JSON."
        )
        interaction["assertions"] = _json_copy(assertions)
        interaction["policy"] = _json_copy(dict(policy))
        self._emit_interaction(interaction_id)

    def _require_interaction(self, interaction_id: str) -> dict[str, Any]:
        interaction = self._interactions.get(interaction_id)
        if interaction is None:
            raise ValueError(f"unknown interaction: {interaction_id}")
        return interaction

    def _emit_interaction(self, interaction_id: str) -> None:
        interaction = self._require_interaction(interaction_id)
        status = str(interaction.get("status"))
        if status not in INTERACTION_STATUSES:
            raise ValueError(f"unsupported interaction status: {status}")
        _reject_forbidden_keys(interaction)
        if self._interaction_sink is not None:
            self._interaction_sink(_json_copy(interaction))
