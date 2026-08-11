"""Behavior tests for the Model Research activity AnyWidget."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("research_activity.py")
JS_PATH = Path(__file__).with_name("research_activity.js")
CSS_PATH = Path(__file__).with_name("research_activity.css")


def load_activity():
    assert MODULE_PATH.is_file(), "missing Model Research activity bridge"
    spec = importlib.util.spec_from_file_location("research_activity", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def event(sequence: int, interaction_id: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "id": f"event-{sequence:04d}",
        "timestamp": "2026-08-07T20:00:00.000Z",
        "phase": "model_request" if interaction_id else "configuration",
        "status": "requested" if interaction_id else "completed",
        "summary": "Requested model interaction."
        if interaction_id
        else "Loaded config.",
    }
    if interaction_id is not None:
        value["interaction_id"] = interaction_id
        value["test_id"] = "ticket"
    return value


def requested_interaction(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "interaction-0001",
        "timestamp": "2026-08-07T20:00:00.000Z",
        "test_id": "ticket",
        "source": "fixture",
        "provenance_label": "Fixture Response — No Provider Contacted",
        "provider": "loopback",
        "model": "fixture-json-v1",
        "system_prompt": None,
        "user_prompt": "Classify a synthetic ticket.",
        "status": "requested",
        "linked_event_ids": ["event-0001"],
    }
    value.update(changes)
    return value


def evaluated_interaction(**changes: object) -> dict[str, object]:
    value = {
        **requested_interaction(),
        "status": "evaluated",
        "linked_event_ids": [
            "event-0001",
            "event-0002",
            "event-0003",
            "event-0004",
            "event-0005",
        ],
        "response": '{"label":"technical"}',
        "parsed": {"label": "technical"},
        "parse_error": None,
        "assertions": [
            {"type": "is-json", "status": "pass", "detail": "", "weight": 1.0}
        ],
        "policy": {"status": "pass", "findings": []},
    }
    value.update(changes)
    return value


def linked_events() -> list[dict[str, object]]:
    return [
        event(1, "interaction-0001"),
        {
            **event(2, "interaction-0001"),
            "phase": "model_response",
            "status": "received",
        },
        {**event(3, "interaction-0001"), "phase": "parse", "status": "parsed"},
        {
            **event(4, "interaction-0001"),
            "phase": "assertion",
            "status": "accepted",
        },
        {**event(5, "interaction-0001"), "phase": "policy", "status": "accepted"},
    ]


def test_widget_preserves_partial_evidence_after_safe_failure() -> None:
    activity = load_activity().ResearchActivity()
    activity.begin_run(1)
    activity.append_event(event(1, "interaction-0001"))
    activity.append_interaction_update(requested_interaction())

    activity.fail_run("Provider request failed safely.")

    assert activity.run_state == "error"
    assert activity.final_status == "error"
    assert activity.safe_message == "Provider request failed safely."
    assert len(activity.events) == 1
    assert len(activity.interactions) == 1


def test_widget_replaces_interaction_updates_without_duplication() -> None:
    activity = load_activity().ResearchActivity()
    activity.begin_run(1)
    for snapshot in linked_events():
        activity.append_event(snapshot)
    activity.append_interaction_update(requested_interaction())
    activity.append_interaction_update(evaluated_interaction())

    assert len(activity.interactions) == 1
    assert activity.interactions[0]["status"] == "evaluated"


def test_widget_rejects_noncontiguous_ids_and_stale_generations() -> None:
    activity = load_activity().ResearchActivity()
    activity.begin_run(2)

    with pytest.raises(ValueError, match="move backwards"):
        activity.begin_run(1)
    with pytest.raises(ValueError, match="contiguous"):
        activity.append_event(event(2))
    with pytest.raises(ValueError, match="contiguous"):
        activity.append_interaction_update(requested_interaction(id="interaction-0002"))


def test_widget_completion_requires_reciprocal_links() -> None:
    activity = load_activity().ResearchActivity()
    activity.begin_run(1)
    activity.append_event(event(1, "interaction-0001"))
    activity.append_interaction_update(requested_interaction())

    activity.complete_run({"final_status": "pass"})

    assert activity.run_state == "completed"
    assert activity.final_status == "pass"

    broken = load_activity().ResearchActivity()
    broken.begin_run(1)
    broken.append_event(event(1, "interaction-0001"))
    broken.append_interaction_update(
        requested_interaction(linked_event_ids=["event-9999"])
    )
    with pytest.raises(ValueError, match="reciprocal"):
        broken.complete_run({"final_status": "pass"})


def test_widget_uses_json_copies_and_resets_for_a_new_generation() -> None:
    activity = load_activity().ResearchActivity()
    activity.begin_run(1)
    snapshot = event(1)
    activity.append_event(snapshot)
    snapshot["summary"] = "mutated outside widget"

    assert activity.events[0]["summary"] == "Loaded config."

    activity.begin_run(2)

    assert activity.generation == 2
    assert activity.events == []
    assert activity.interactions == []
    assert activity.run_state == "running"
    assert activity.final_status == ""


def test_widget_assets_are_local_and_use_model_research_vocabulary() -> None:
    module = load_activity()

    assert module.ResearchActivity._esm._path == JS_PATH
    assert module.ResearchActivity._css._path == CSS_PATH
    assert "Run Activity" in JS_PATH.read_text(encoding="utf-8")
    assert "Model Interactions" in JS_PATH.read_text(encoding="utf-8")
    assert "LLM Interactions" not in JS_PATH.read_text(encoding="utf-8")
