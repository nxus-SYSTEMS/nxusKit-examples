"""Safe, side-effect-free run-event projection for Reasoning Lab frontends."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable


CATEGORIES = {"run", "provider", "facts", "engine", "repair"}
STATUSES = {
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
MAX_MESSAGE_LENGTH = 240
MAX_COMPONENT_VALUE_LENGTH = 120
_INTERACTION_ID = re.compile(r"llm-[0-9]{4}")


def _system_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_hundredths(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("event timestamp must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    hundredths = normalized.microsecond // 10_000
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{hundredths:02d}Z"


class RunEventEmitter:
    """Validate and sequence safe run events without owning any execution."""

    def __init__(
        self,
        sink: Callable[[dict[str, Any]], None] | None = None,
        utcnow: Callable[[], datetime] = _system_utcnow,
    ) -> None:
        self._sink = sink
        self._utcnow = utcnow
        self._sequence = 0

    def emit(
        self,
        category: str,
        status: str,
        message: str,
        *,
        attempt: int | None = None,
        component: dict[str, str] | None = None,
        llm_interaction_id: str | None = None,
    ) -> dict[str, Any]:
        if category not in CATEGORIES:
            raise ValueError("event category is not allowlisted")
        if status not in STATUSES:
            raise ValueError("event status is not allowlisted")
        if (
            not isinstance(message, str)
            or not message
            or len(message) > MAX_MESSAGE_LENGTH
        ):
            raise ValueError("event message must contain 1 to 240 characters")
        if "\n" in message or "\r" in message:
            raise ValueError("event message must be a single line")
        if attempt is not None and (not isinstance(attempt, int) or attempt < 1):
            raise ValueError("event attempt must be a positive integer")
        if llm_interaction_id is not None and (
            not isinstance(llm_interaction_id, str)
            or _INTERACTION_ID.fullmatch(llm_interaction_id) is None
        ):
            raise ValueError("event interaction ID must use llm-NNNN format")

        safe_component: dict[str, str] | None = None
        if component is not None:
            if not isinstance(component, dict) or not set(component) <= COMPONENT_KEYS:
                raise ValueError("event component contains non-allowlisted keys")
            safe_component = {}
            for key, value in component.items():
                if (
                    not isinstance(value, str)
                    or not value
                    or len(value) > MAX_COMPONENT_VALUE_LENGTH
                    or "\n" in value
                    or "\r" in value
                ):
                    raise ValueError("event component value is invalid")
                safe_component[key] = value

        timestamp = _timestamp_hundredths(self._utcnow())
        self._sequence += 1
        event: dict[str, Any] = {
            "id": f"event-{self._sequence:04d}",
            "sequence": self._sequence,
            "timestamp_utc": timestamp,
            "category": category,
            "status": status,
            "message": message,
        }
        if attempt is not None:
            event["attempt"] = attempt
        if safe_component is not None:
            event["component"] = safe_component
        if llm_interaction_id is not None:
            event["llm_interaction_id"] = llm_interaction_id
        if self._sink is not None:
            published = {**event}
            if safe_component is not None:
                published["component"] = dict(safe_component)
            self._sink(published)
        return event
