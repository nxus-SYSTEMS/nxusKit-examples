"""Unit tests for the safe Reasoning Lab run-event contract."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("run_events.py")


def load_events():
    spec = importlib.util.spec_from_file_location("csg_run_events", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_emitter_assigns_sequence_and_hundredth_utc_timestamp() -> None:
    events = []
    emitter = load_events().RunEventEmitter(
        sink=events.append,
        utcnow=lambda: datetime(2026, 8, 3, 22, 24, 18, 279_999, tzinfo=timezone.utc),
    )

    emitted = emitter.emit(
        "engine",
        "fail",
        "Car remains at home.",
        attempt=1,
        component={"kind": "engine", "id": "clips", "tier": "community"},
    )

    assert emitted == events[0]
    assert emitted["sequence"] == 1
    assert emitted["id"] == "event-0001"
    assert emitted["timestamp_utc"] == "2026-08-03T22:24:18.27Z"


def test_event_has_stable_id_and_optional_interaction_link() -> None:
    emitter = load_events().RunEventEmitter()

    event = emitter.emit(
        "provider",
        "requested",
        "Requesting the baseline recommendation.",
        attempt=1,
        llm_interaction_id="llm-0001",
    )

    assert event["id"] == "event-0001"
    assert event["llm_interaction_id"] == "llm-0001"


@pytest.mark.parametrize("status", ["requested", "received", "accepted", "rejected"])
def test_decision_and_provider_statuses_are_allowlisted(status: str) -> None:
    emitted = load_events().RunEventEmitter().emit("run", status, "Safe event.")

    assert emitted["status"] == status


@pytest.mark.parametrize(
    ("category", "status", "message", "component"),
    [
        ("network", "started", "Starting.", None),
        ("run", "unknown", "Starting.", None),
        ("run", "started", "two\nlines", None),
        ("run", "started", "x" * 241, None),
        ("run", "started", "Starting.", {"secret": "canary"}),
    ],
)
def test_emitter_rejects_non_allowlisted_or_unsafe_event_content(
    category: str,
    status: str,
    message: str,
    component: dict[str, str] | None,
) -> None:
    events = []
    emitter = load_events().RunEventEmitter(sink=events.append)

    with pytest.raises(ValueError):
        emitter.emit(category, status, message, component=component)

    assert events == []


@pytest.mark.parametrize("interaction_id", ["llm-1", "call-0001", "llm-00001"])
def test_emitter_rejects_invalid_interaction_links(interaction_id: str) -> None:
    with pytest.raises(ValueError, match="llm-NNNN"):
        load_events().RunEventEmitter().emit(
            "provider",
            "requested",
            "Requesting a provider response.",
            llm_interaction_id=interaction_id,
        )
