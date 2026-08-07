"""Safe, side-effect-free LLM interaction records for Reasoning Lab frontends."""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


PHASES = {
    "initial_recommendation",
    "fact_extraction",
    "fact_extraction_repair",
    "repaired_recommendation",
}
SOURCES = {"live", "fixture"}
STATUSES = {"requested", "received", "stopped"}
OUTCOME_STATUSES = {"accepted", "rejected", "not_evaluated"}
OUTCOME_DELTAS = {
    "eliminated",
    "decreased",
    "unchanged",
    "increased",
    "not_comparable",
}
INTERACTION_KEYS = {
    "id",
    "linked_event_ids",
    "response_attempt",
    "phase",
    "source",
    "provider",
    "model",
    "status",
    "requested_at_utc",
    "completed_at_utc",
    "messages",
    "response_content",
    "safe_error",
    "repair_context",
    "outcome",
}
BASE_INTERACTION_KEYS = INTERACTION_KEYS - {"repair_context", "outcome"}
IMMUTABLE_FIELDS = {
    "id",
    "response_attempt",
    "phase",
    "source",
    "provider",
    "model",
    "requested_at_utc",
    "messages",
}
MAX_APPLICATION_CONTENT_LENGTH = 200_000
MAX_IDENTITY_LENGTH = 120
MAX_SAFE_ERROR_LENGTH = 240
_INTERACTION_ID = re.compile(r"llm-[0-9]{4}")
_EVENT_ID = re.compile(r"event-[0-9]{4}")
_UTC_HUNDREDTHS = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{2}Z"
)


@dataclass(frozen=True)
class LLMCallContext:
    """Immutable identity for one application-level LLM call."""

    phase: Literal[
        "initial_recommendation",
        "fact_extraction",
        "fact_extraction_repair",
        "repaired_recommendation",
    ]
    response_attempt: int
    source: Literal["live", "fixture"]
    provider: str
    model: str


def _system_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_hundredths(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("LLM interaction timestamp must be timezone-aware")
    normalized = value.astimezone(timezone.utc)
    hundredths = normalized.microsecond // 10_000
    return normalized.strftime("%Y-%m-%dT%H:%M:%S") + f".{hundredths:02d}Z"


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("LLM interaction content must be JSON-safe") from exc


def _validate_timestamp(value: Any, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _UTC_HUNDREDTHS.fullmatch(value) is None:
        raise ValueError("LLM interaction timestamp must use UTC hundredths")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise ValueError("LLM interaction timestamp must use UTC hundredths") from exc
    return value


def _validate_positive_int(value: Any, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(message)
    return value


def _validate_nonnegative_int(value: Any, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(message)
    return value


def _validate_identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_IDENTITY_LENGTH
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{label} must contain 1 to 120 single-line characters")
    return value


def _validate_content(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_APPLICATION_CONTENT_LENGTH:
        raise ValueError(f"{label} must contain at most 200000 characters")
    return value


def _validate_string_list(
    value: Any,
    label: str,
    *,
    allow_empty: bool = True,
    single_line: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{label} must be a list of strings")
    result = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{label} must be a list of strings")
        if len(item) > MAX_APPLICATION_CONTENT_LENGTH:
            raise ValueError(f"{label} items must contain at most 200000 characters")
        if single_line and ("\n" in item or "\r" in item):
            raise ValueError(f"{label} items must be single-line strings")
        result.append(item)
    return result


def _validate_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("LLM interaction must contain exactly two messages")
    expected_roles = ("system", "user")
    result = []
    for message, expected_role in zip(value, expected_roles, strict=True):
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ValueError("LLM message must contain only role and content")
        if message["role"] != expected_role:
            raise ValueError("LLM message role or order is invalid")
        content = _validate_content(message["content"], "LLM message content")
        result.append({"role": expected_role, "content": content})
    return result


def _validate_repair_context(value: Any) -> dict[str, Any]:
    required = {
        "repair_attempt",
        "triggering_engines",
        "blocking_finding_count",
        "repair_instructions",
        "prompt_delta",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("repair context fields are invalid")
    prompt_change = value["prompt_delta"]
    if not isinstance(prompt_change, dict) or set(prompt_change) != {
        "added",
        "removed",
    }:
        raise ValueError("prompt delta fields are invalid")
    return {
        "repair_attempt": _validate_positive_int(
            value["repair_attempt"], "repair attempt must be a positive integer"
        ),
        "triggering_engines": _validate_string_list(
            value["triggering_engines"],
            "triggering engines",
            allow_empty=False,
            single_line=True,
        ),
        "blocking_finding_count": _validate_nonnegative_int(
            value["blocking_finding_count"],
            "repair blocking-finding count must be a nonnegative integer",
        ),
        "repair_instructions": _validate_string_list(
            value["repair_instructions"], "repair instructions", allow_empty=False
        ),
        "prompt_delta": {
            "added": _validate_string_list(
                prompt_change["added"], "added prompt lines"
            ),
            "removed": _validate_string_list(
                prompt_change["removed"], "removed prompt lines"
            ),
        },
    }


def _measured_delta(current: int, previous: int | None) -> str:
    if previous is None:
        return "not_comparable"
    if current == 0 and previous > 0:
        return "eliminated"
    if current < previous:
        return "decreased"
    if current == previous:
        return "unchanged"
    return "increased"


def _validate_outcome(value: Any) -> dict[str, Any]:
    required = {
        "status",
        "blocking_finding_count",
        "previous_blocking_finding_count",
        "delta",
        "engines",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("outcome fields are invalid")
    if value["status"] not in OUTCOME_STATUSES:
        raise ValueError("outcome status is not allowlisted")
    current = _validate_nonnegative_int(
        value["blocking_finding_count"],
        "outcome blocking-finding count must be a nonnegative integer",
    )
    if (value["status"] == "accepted" and current != 0) or (
        value["status"] == "rejected" and current == 0
    ):
        raise ValueError("outcome status does not match blocking-finding count")
    previous_raw = value["previous_blocking_finding_count"]
    previous = (
        None
        if previous_raw is None
        else _validate_nonnegative_int(
            previous_raw,
            "previous blocking-finding count must be a nonnegative integer or null",
        )
    )
    if value["delta"] not in OUTCOME_DELTAS:
        raise ValueError("outcome delta is not allowlisted")
    if value["delta"] != _measured_delta(current, previous):
        raise ValueError("outcome delta does not match measured finding counts")
    engines_raw = value["engines"]
    if not isinstance(engines_raw, list):
        raise ValueError("outcome engines must be a list")
    engines = []
    seen_ids = set()
    for engine in engines_raw:
        if not isinstance(engine, dict) or set(engine) != {
            "id",
            "status",
            "blocking_finding_count",
        }:
            raise ValueError("outcome engine fields are invalid")
        engine_id = _validate_identity(engine["id"], "outcome engine ID")
        if engine_id in seen_ids:
            raise ValueError("outcome engine IDs must be unique")
        seen_ids.add(engine_id)
        if engine["status"] not in OUTCOME_STATUSES:
            raise ValueError("outcome engine status is not allowlisted")
        engines.append(
            {
                "id": engine_id,
                "status": engine["status"],
                "blocking_finding_count": _validate_nonnegative_int(
                    engine["blocking_finding_count"],
                    "engine blocking-finding count must be a nonnegative integer",
                ),
            }
        )
    return {
        "status": value["status"],
        "blocking_finding_count": current,
        "previous_blocking_finding_count": previous,
        "delta": value["delta"],
        "engines": engines,
    }


def validate_interaction_snapshot(
    raw: Mapping[str, Any], previous: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return a detached, allowlisted snapshot or fail closed."""

    if not isinstance(raw, Mapping):
        raise ValueError("LLM interaction snapshot must be a mapping")
    keys = set(raw)
    if not BASE_INTERACTION_KEYS <= keys or not keys <= INTERACTION_KEYS:
        raise ValueError("LLM interaction snapshot fields are invalid")

    interaction_id = raw["id"]
    if (
        not isinstance(interaction_id, str)
        or _INTERACTION_ID.fullmatch(interaction_id) is None
    ):
        raise ValueError("LLM interaction ID must use llm-NNNN format")

    links_raw = raw["linked_event_ids"]
    if not isinstance(links_raw, list):
        raise ValueError("linked event IDs must be a list")
    links = []
    for event_id in links_raw:
        if not isinstance(event_id, str) or _EVENT_ID.fullmatch(event_id) is None:
            raise ValueError("linked event ID must use event-NNNN format")
        if event_id in links:
            raise ValueError("linked event IDs must be unique")
        links.append(event_id)

    phase = raw["phase"]
    if phase not in PHASES:
        raise ValueError("LLM interaction phase is not allowlisted")
    source = raw["source"]
    if source not in SOURCES:
        raise ValueError("LLM interaction source is not allowlisted")
    status = raw["status"]
    if status not in STATUSES:
        raise ValueError("LLM interaction status is not allowlisted")

    requested_at = _validate_timestamp(raw["requested_at_utc"])
    completed_at = _validate_timestamp(raw["completed_at_utc"], optional=True)
    messages = _validate_messages(raw["messages"])
    response_content = _validate_content(
        raw["response_content"], "LLM response content", optional=True
    )
    safe_error = raw["safe_error"]
    if safe_error is not None and (
        not isinstance(safe_error, str)
        or not safe_error
        or len(safe_error) > MAX_SAFE_ERROR_LENGTH
        or "\n" in safe_error
        or "\r" in safe_error
    ):
        raise ValueError("safe error must contain 1 to 240 single-line characters")

    if status == "requested" and (
        completed_at is not None
        or response_content is not None
        or safe_error is not None
    ):
        raise ValueError("requested interaction cannot contain a result")
    if status == "received" and (
        completed_at is None or response_content is None or safe_error is not None
    ):
        raise ValueError("received interaction must contain only response content")
    if status == "stopped" and (
        completed_at is None or response_content is not None or safe_error is None
    ):
        raise ValueError("stopped interaction must contain only a safe error")

    safe: dict[str, Any] = {
        "id": interaction_id,
        "linked_event_ids": links,
        "response_attempt": _validate_positive_int(
            raw["response_attempt"],
            "response attempt must be a positive integer",
        ),
        "phase": phase,
        "source": source,
        "provider": _validate_identity(raw["provider"], "provider"),
        "model": _validate_identity(raw["model"], "model"),
        "status": status,
        "requested_at_utc": requested_at,
        "completed_at_utc": completed_at,
        "messages": messages,
        "response_content": response_content,
        "safe_error": safe_error,
    }
    if "repair_context" in raw:
        if phase != "repaired_recommendation":
            raise ValueError(
                "repair context is only valid for a repaired recommendation"
            )
        safe["repair_context"] = _validate_repair_context(raw["repair_context"])
    if "outcome" in raw:
        if phase not in {"initial_recommendation", "repaired_recommendation"} or (
            status != "received"
        ):
            raise ValueError("outcome is only valid for a received recommendation")
        safe["outcome"] = _validate_outcome(raw["outcome"])

    if previous is not None:
        prior = _json_copy(previous)
        for field in IMMUTABLE_FIELDS:
            if safe[field] != prior[field]:
                raise ValueError("immutable interaction field changed")
        prior_links = prior["linked_event_ids"]
        if safe["linked_event_ids"][: len(prior_links)] != prior_links:
            raise ValueError("linked event IDs cannot be removed or reordered")
        if prior["status"] in {"received", "stopped"}:
            if safe["status"] != prior["status"]:
                raise ValueError("terminal interaction cannot change status")
            for field in ("completed_at_utc", "response_content", "safe_error"):
                if safe[field] != prior[field]:
                    raise ValueError("terminal interaction cannot change result")
        elif safe["status"] not in STATUSES:
            raise ValueError("interaction transition is invalid")
        if (
            "repair_context" in prior
            and safe.get("repair_context") != prior["repair_context"]
        ):
            raise ValueError("repair context cannot change")
        if "outcome" in prior and safe.get("outcome") != prior["outcome"]:
            raise ValueError("interaction outcome cannot change")

    return _json_copy(safe)


def prompt_delta(previous: str, current: str) -> dict[str, list[str]]:
    """Return a deterministic line-oriented prompt delta."""

    _validate_content(previous, "previous prompt")
    _validate_content(current, "current prompt")
    added = []
    removed = []
    for line in difflib.ndiff(previous.splitlines(), current.splitlines()):
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
    return {"added": added, "removed": removed}


class LLMInteractionRecorder:
    """Validate and publish immutable interaction snapshots without executing calls."""

    def __init__(
        self,
        sink: Callable[[dict[str, Any]], None] | None = None,
        utcnow: Callable[[], datetime] = _system_utcnow,
    ) -> None:
        self._sink = sink
        self._utcnow = utcnow
        self._interactions: list[dict[str, Any]] = []

    def _publish(self, index: int, snapshot: Mapping[str, Any]) -> None:
        previous = (
            self._interactions[index] if index < len(self._interactions) else None
        )
        safe = validate_interaction_snapshot(snapshot, previous=previous)
        if previous is None:
            self._interactions.append(safe)
        else:
            self._interactions[index] = safe
        if self._sink is not None:
            self._sink(_json_copy(safe))

    def _index(self, interaction_id: str) -> int:
        for index, item in enumerate(self._interactions):
            if item["id"] == interaction_id:
                return index
        raise ValueError("LLM interaction ID is unknown")

    def begin(
        self,
        context: LLMCallContext,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        interaction_id = f"llm-{len(self._interactions) + 1:04d}"
        requested_at = _timestamp_hundredths(self._utcnow())
        self._publish(
            len(self._interactions),
            {
                "id": interaction_id,
                "linked_event_ids": [],
                "response_attempt": context.response_attempt,
                "phase": context.phase,
                "source": context.source,
                "provider": context.provider,
                "model": context.model,
                "status": "requested",
                "requested_at_utc": requested_at,
                "completed_at_utc": None,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_content": None,
                "safe_error": None,
            },
        )
        return interaction_id

    def link_event(self, interaction_id: str, event_id: str) -> None:
        index = self._index(interaction_id)
        current = self._interactions[index]
        links = [*current["linked_event_ids"]]
        if event_id not in links:
            links.append(event_id)
        self._publish(index, {**current, "linked_event_ids": links})

    def complete(self, interaction_id: str, response_content: str) -> None:
        index = self._index(interaction_id)
        current = self._interactions[index]
        if current["status"] != "requested":
            raise ValueError("only a requested interaction can be completed")
        self._publish(
            index,
            {
                **current,
                "status": "received",
                "completed_at_utc": _timestamp_hundredths(self._utcnow()),
                "response_content": response_content,
                "safe_error": None,
            },
        )

    def stop(self, interaction_id: str, safe_error: str) -> None:
        index = self._index(interaction_id)
        current = self._interactions[index]
        if current["status"] != "requested":
            raise ValueError("only a requested interaction can be stopped")
        self._publish(
            index,
            {
                **current,
                "status": "stopped",
                "completed_at_utc": _timestamp_hundredths(self._utcnow()),
                "response_content": None,
                "safe_error": safe_error,
            },
        )

    def annotate_repair(
        self, interaction_id: str, repair_context: Mapping[str, Any]
    ) -> None:
        index = self._index(interaction_id)
        self._publish(
            index,
            {
                **self._interactions[index],
                "repair_context": _json_copy(repair_context),
            },
        )

    def annotate_outcome(
        self, response_attempt: int, outcome: Mapping[str, Any]
    ) -> None:
        matching = [
            index
            for index, item in enumerate(self._interactions)
            if item["response_attempt"] == response_attempt
            and item["phase"] in {"initial_recommendation", "repaired_recommendation"}
            and item["status"] == "received"
            and "outcome" not in item
        ]
        if len(matching) != 1:
            raise ValueError("response attempt must identify one recommendation")
        index = matching[0]
        self._publish(
            index,
            {
                **self._interactions[index],
                "outcome": _json_copy(outcome),
            },
        )
