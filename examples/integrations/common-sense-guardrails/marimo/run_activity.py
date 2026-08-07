"""AnyWidget state bridge for run activity and versioned session export."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import anywidget
import traitlets

from session_export import (
    _safe_events,
    build_session_document,
    configurations_match,
    export_filename,
    normalize_configuration,
    serialize_session_document,
)

PYTHON_ROOT = Path(__file__).resolve().parents[1] / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from llm_interactions import validate_interaction_snapshot  # noqa: E402


EXPORT_CHOICES = {"original_with_results", "draft_settings_only"}


def _safe_linked_events(events: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unlinked = []
    for raw in events:
        event = dict(raw)
        event.pop("id", None)
        event.pop("llm_interaction_id", None)
        unlinked.append(event)
    validated = _safe_events(unlinked)
    result = []
    for expected_sequence, (raw, safe) in enumerate(
        zip(events, validated, strict=True), start=1
    ):
        event_id = raw.get("id")
        if event_id != f"event-{expected_sequence:04d}":
            raise ValueError("event IDs must be contiguous")
        linked_id = raw.get("llm_interaction_id")
        if linked_id is not None and not (
            isinstance(linked_id, str)
            and len(linked_id) == 8
            and linked_id.startswith("llm-")
            and linked_id[4:].isdigit()
        ):
            raise ValueError("event interaction ID must use llm-NNNN format")
        linked = {"id": event_id, **safe}
        if linked_id is not None:
            linked["llm_interaction_id"] = linked_id
        result.append(linked)
    return result


def _system_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc_hundredths(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    hundredths = normalized.microsecond // 10_000
    whole_seconds = normalized.replace(microsecond=0).isoformat().removesuffix("+00:00")
    return f"{whole_seconds}.{hundredths:02d}Z"


class RunActivity(anywidget.AnyWidget):
    """Hold safe run state while browser code renders and downloads it."""

    _esm = Path(__file__).with_name("run_activity.js")
    _css = Path(__file__).with_name("run_activity.css")

    events = traitlets.List(trait=traitlets.Dict(), default_value=[]).tag(sync=True)
    interactions = traitlets.List(trait=traitlets.Dict(), default_value=[]).tag(
        sync=True
    )
    include_full_transcript = traitlets.Bool(False).tag(sync=True)
    state = traitlets.Unicode("idle").tag(sync=True)
    submitted_configuration = traitlets.Dict(default_value={}).tag(sync=True)
    draft_configuration = traitlets.Dict(default_value={}).tag(sync=True)
    draft_differs = traitlets.Bool(False).tag(sync=True)
    final_elapsed_ms = traitlets.Int(0).tag(sync=True)
    has_results = traitlets.Bool(False).tag(sync=True)
    export_choice = traitlets.Unicode("original_with_results").tag(sync=True)
    export_generation = traitlets.Int(0).tag(sync=True)
    export_ready_generation = traitlets.Int(0).tag(sync=True)
    export_json = traitlets.Unicode("").tag(sync=True)
    export_filename = traitlets.Unicode("").tag(sync=True)
    export_error = traitlets.Unicode("").tag(sync=True)
    prepared_export_choice = traitlets.Unicode("").tag(sync=True)

    def __init__(
        self,
        *,
        utcnow: Callable[[], datetime] = _system_utcnow,
        **kwargs: object,
    ) -> None:
        self._utcnow = utcnow
        self._response: dict[str, Any] | None = None
        self._generation = 0
        self._started_at: datetime | None = None
        super().__init__(**kwargs)
        self.observe(self._handle_export_generation, names="export_generation")
        self.observe(self._handle_export_choice, names="export_choice")
        self.observe(
            self._handle_include_full_transcript, names="include_full_transcript"
        )

    def set_draft_configuration(self, configuration: Mapping[str, Any]) -> None:
        normalized = normalize_configuration(configuration)
        self.draft_configuration = normalized
        self.draft_differs = bool(
            self.has_results
            and self.submitted_configuration
            and not configurations_match(normalized, self.submitted_configuration)
        )
        if (
            self.has_results
            and not self.draft_differs
            and self.export_choice != "original_with_results"
        ):
            self.export_choice = "original_with_results"
        else:
            self._prepare_export()

    def begin_run(
        self,
        configuration: Mapping[str, Any],
        *,
        generation: int | None = None,
    ) -> None:
        if generation is not None:
            if generation < 1:
                raise ValueError("run generation must be positive")
            if generation == self._generation:
                return
            if generation < self._generation:
                raise ValueError("run generation cannot move backwards")
            self._generation = generation
        normalized = normalize_configuration(configuration)
        self.submitted_configuration = normalized
        if not self.draft_configuration:
            self.draft_configuration = dict(normalized)
        self.events = []
        self.interactions = []
        self.include_full_transcript = False
        self.state = "running"
        self.final_elapsed_ms = 0
        self.has_results = False
        self.draft_differs = False
        self._response = None
        self._started_at = self._utcnow()
        self.export_json = ""
        self.export_filename = ""
        self.export_error = ""
        self.prepared_export_choice = ""
        self.export_choice = "original_with_results"
        self._prepare_export()

    def append_event(self, event: Mapping[str, Any]) -> None:
        self.events = _safe_linked_events([*self.events, dict(event)])

    def append_interaction_update(self, snapshot: Mapping[str, Any]) -> None:
        interaction_id = snapshot.get("id")
        matching = [
            index
            for index, item in enumerate(self.interactions)
            if item.get("id") == interaction_id
        ]
        if len(matching) > 1:
            raise ValueError("LLM interaction IDs must be unique")
        if matching:
            index = matching[0]
            safe = validate_interaction_snapshot(
                snapshot, previous=self.interactions[index]
            )
            updated = [dict(item) for item in self.interactions]
            updated[index] = safe
            self.interactions = updated
            return
        expected_id = f"llm-{len(self.interactions) + 1:04d}"
        if interaction_id != expected_id:
            raise ValueError("LLM interaction IDs must be contiguous")
        safe = validate_interaction_snapshot(snapshot)
        self.interactions = [*self.interactions, safe]

    def complete_run(self, response: Mapping[str, Any]) -> None:
        self._complete_run(response, validated_at=self._utcnow())

    def _complete_run(
        self,
        response: Mapping[str, Any],
        *,
        validated_at: datetime,
    ) -> None:
        safe_events = _safe_linked_events(self.events)
        if response.get("llm_interactions", []) != self.interactions:
            raise ValueError("response interactions do not match observed UI state")
        validated = build_session_document(
            self.submitted_configuration,
            response=response,
            events=safe_events,
            llm_interactions=self.interactions,
            exported_at=validated_at,
        )
        results = validated["results"]
        assert isinstance(results, dict)
        safe_response = dict(results["response"])
        safe_response["run_receipt"] = dict(results["run_receipt"])
        self._response = safe_response
        self.events = safe_events
        self.final_elapsed_ms = int(results["run_receipt"]["elapsed_ms"])
        receipt_status = str(results["run_receipt"]["status"])
        self.state = "completed" if receipt_status == "completed" else receipt_status
        self.has_results = True
        self._started_at = None
        self.draft_differs = not configurations_match(
            self.draft_configuration or self.submitted_configuration,
            self.submitted_configuration,
        )
        self._prepare_export(exported_at=validated_at)

    def fail_run(self, message: str) -> None:
        completed_at = self._utcnow()
        started_at = self._started_at or completed_at
        elapsed_ms = max(0, round((completed_at - started_at).total_seconds() * 1_000))
        self.append_event(
            {
                "id": f"event-{len(self.events) + 1:04d}",
                "sequence": len(self.events) + 1,
                "timestamp_utc": _utc_hundredths(completed_at),
                "category": "run",
                "status": "stopped",
                "message": message,
            }
        )
        response = {
            "mode": self.submitted_configuration.get("mode"),
            "record": None,
            "message": message,
            "llm_interactions": json.loads(
                json.dumps(self.interactions, ensure_ascii=False)
            ),
            "run_receipt": {
                "started_at_utc": _utc_hundredths(started_at),
                "completed_at_utc": _utc_hundredths(completed_at),
                "elapsed_ms": elapsed_ms,
                "status": "failed",
            },
        }
        self._complete_run(response, validated_at=completed_at)

    def _handle_export_generation(self, change: Mapping[str, object]) -> None:
        generation = int(change.get("new") or 0)
        if generation < 1:
            return
        self._prepare_export()
        self.export_ready_generation = generation

    def _handle_export_choice(self, change: Mapping[str, object]) -> None:
        if change.get("new") == change.get("old"):
            return
        if change.get("new") == "draft_settings_only" and self.include_full_transcript:
            self.include_full_transcript = False
            return
        self._prepare_export()

    def _handle_include_full_transcript(self, change: Mapping[str, object]) -> None:
        if change.get("new") == change.get("old"):
            return
        if bool(change.get("new")) and (
            not self.has_results or self.export_choice == "draft_settings_only"
        ):
            self.include_full_transcript = False
            return
        self._prepare_export()

    def _prepare_export(self, *, exported_at: datetime | None = None) -> None:
        self.export_json = ""
        self.export_filename = ""
        self.export_error = ""
        self.prepared_export_choice = ""
        try:
            if self.export_choice not in EXPORT_CHOICES:
                raise ValueError("export choice is invalid")
            if self._response is None or self.export_choice == "draft_settings_only":
                configuration = self.draft_configuration
                response = None
                events = []
            else:
                configuration = self.submitted_configuration
                response = self._response
                events = self.events
            if not configuration:
                raise ValueError("export configuration is unavailable")
            exported_at = exported_at or self._utcnow()
            document = build_session_document(
                configuration,
                response=response,
                events=events,
                llm_interactions=self.interactions,
                include_full_transcript=bool(
                    self.include_full_transcript
                    and self.has_results
                    and response is not None
                    and self.export_choice == "original_with_results"
                ),
                exported_at=exported_at,
            )
            self.export_json = serialize_session_document(document)
            self.export_filename = export_filename(
                document["configuration"]["scenario"], exported_at
            )
            self.prepared_export_choice = self.export_choice
        except (TypeError, ValueError):
            self.export_error = "Export could not be prepared from the current session."
