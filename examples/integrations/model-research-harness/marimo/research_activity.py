"""AnyWidget state bridge for Model Research activity evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anywidget
import traitlets


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("activity snapshots must be JSON-compatible") from exc


def _require_contiguous_id(value: object, prefix: str, sequence: int) -> None:
    if value != f"{prefix}-{sequence:04d}":
        raise ValueError(f"{prefix} IDs must be contiguous")


def _validate_reciprocal_links(
    events: list[dict[str, Any]], interactions: list[dict[str, Any]]
) -> None:
    events_by_id = {str(event["id"]): event for event in events}
    interactions_by_id = {
        str(interaction["id"]): interaction for interaction in interactions
    }
    for event in events:
        interaction_id = event.get("interaction_id")
        if interaction_id is None:
            continue
        interaction = interactions_by_id.get(str(interaction_id))
        if interaction is None or event["id"] not in interaction.get(
            "linked_event_ids", []
        ):
            raise ValueError("event and interaction links must be reciprocal")
    for interaction in interactions:
        for event_id in interaction.get("linked_event_ids", []):
            event = events_by_id.get(str(event_id))
            if event is None or event.get("interaction_id") != interaction["id"]:
                raise ValueError("event and interaction links must be reciprocal")


class ResearchActivity(anywidget.AnyWidget):
    """Retain immutable activity snapshots for one submitted generation."""

    _esm = Path(__file__).with_name("research_activity.js")
    _css = Path(__file__).with_name("research_activity.css")

    events = traitlets.List(trait=traitlets.Dict(), default_value=[]).tag(sync=True)
    interactions = traitlets.List(trait=traitlets.Dict(), default_value=[]).tag(
        sync=True
    )
    run_state = traitlets.Unicode("idle").tag(sync=True)
    generation = traitlets.Int(0).tag(sync=True)
    final_status = traitlets.Unicode("").tag(sync=True)
    safe_message = traitlets.Unicode("").tag(sync=True)

    def begin_run(self, generation: int) -> None:
        if generation < 1:
            raise ValueError("run generation must be positive")
        if generation == self.generation:
            return
        if generation < self.generation:
            raise ValueError("run generation cannot move backwards")
        self.generation = generation
        self.events = []
        self.interactions = []
        self.run_state = "running"
        self.final_status = ""
        self.safe_message = ""

    def append_event(self, snapshot: Mapping[str, Any]) -> None:
        safe = _json_copy(dict(snapshot))
        _require_contiguous_id(safe.get("id"), "event", len(self.events) + 1)
        self.events = [*_json_copy(self.events), safe]

    def append_interaction_update(self, snapshot: Mapping[str, Any]) -> None:
        safe = _json_copy(dict(snapshot))
        interaction_id = safe.get("id")
        matching = [
            index
            for index, interaction in enumerate(self.interactions)
            if interaction.get("id") == interaction_id
        ]
        if len(matching) > 1:
            raise ValueError("interaction IDs must be unique")
        if not matching:
            _require_contiguous_id(
                interaction_id, "interaction", len(self.interactions) + 1
            )
            self.interactions = [*_json_copy(self.interactions), safe]
            return

        index = matching[0]
        previous = self.interactions[index]
        for field in (
            "id",
            "timestamp",
            "test_id",
            "source",
            "provenance_label",
            "provider",
            "model",
            "system_prompt",
            "user_prompt",
        ):
            if safe.get(field) != previous.get(field):
                raise ValueError(f"interaction field is immutable: {field}")
        previous_links = list(previous.get("linked_event_ids", []))
        current_links = list(safe.get("linked_event_ids", []))
        if current_links[: len(previous_links)] != previous_links:
            raise ValueError("interaction event links must be append-only")
        updated = _json_copy(self.interactions)
        updated[index] = safe
        self.interactions = updated

    def complete_run(self, report: Mapping[str, Any]) -> None:
        _validate_reciprocal_links(self.events, self.interactions)
        safe_report = _json_copy(dict(report))
        self.final_status = str(safe_report.get("final_status", "completed"))
        self.run_state = "completed"
        self.safe_message = ""

    def fail_run(self, safe_message: str) -> None:
        self.final_status = "error"
        self.safe_message = str(safe_message)
        self.run_state = "error"
