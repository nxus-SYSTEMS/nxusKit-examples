"""Behavior tests for the Reasoning Lab run-activity AnyWidget."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("run_activity.py")
JS_PATH = Path(__file__).with_name("run_activity.js")
CSS_PATH = Path(__file__).with_name("run_activity.css")


def load_activity():
    spec = importlib.util.spec_from_file_location("run_activity", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configuration(**overrides):
    value = {
        "scenario": "car-wash",
        "mode": "live",
        "provider": "ollama",
        "model": "llama3:8b",
        "mechanisms": ["clips", "solver"],
        "max_repair_attempts": 3,
    }
    value.update(overrides)
    return value


def event(
    sequence: int,
    category: str,
    status: str,
    *,
    llm_interaction_id: str | None = None,
) -> dict:
    value = {
        "id": f"event-{sequence:04d}",
        "sequence": sequence,
        "timestamp_utc": "2026-08-03T22:24:18.27Z",
        "category": category,
        "status": status,
        "message": f"{category} {status}.",
    }
    if llm_interaction_id is not None:
        value["llm_interaction_id"] = llm_interaction_id
    return value


def requested_interaction(**changes) -> dict:
    value = {
        "id": "llm-0001",
        "linked_event_ids": ["event-0001"],
        "response_attempt": 1,
        "phase": "initial_recommendation",
        "source": "live",
        "provider": "ollama",
        "model": "llama3:8b",
        "status": "requested",
        "requested_at_utc": "2026-08-04T15:30:00.12Z",
        "completed_at_utc": None,
        "messages": [
            {"role": "system", "content": "Answer directly."},
            {"role": "user", "content": "Choose a safe route."},
        ],
        "response_content": None,
        "safe_error": None,
    }
    value.update(changes)
    return value


def received_interaction(**changes) -> dict:
    value = {
        **requested_interaction(),
        "linked_event_ids": ["event-0001", "event-0002"],
        "status": "received",
        "completed_at_utc": "2026-08-04T15:30:01.34Z",
        "response_content": "Use the certified route.",
    }
    value.update(changes)
    return value


def response(
    *,
    elapsed_ms: int = 43_082,
    status: str = "completed",
    llm_interactions: list[dict] | None = None,
) -> dict:
    value = {
        "mode": "live",
        "record": {"schema_version": "1.0.0", "scenario": {"id": "car-wash"}},
        "message": "Record built after explicit Analyze selection.",
        "run_receipt": {
            "started_at_utc": "2026-08-03T22:24:18.27Z",
            "completed_at_utc": "2026-08-03T22:25:01.35Z",
            "elapsed_ms": elapsed_ms,
            "status": status,
        },
    }
    if llm_interactions is not None:
        value["llm_interactions"] = llm_interactions
    return value


def test_explicit_transcript_choice_prepares_linked_v2_export() -> None:
    activity = load_activity().RunActivity()
    activity.set_draft_configuration(configuration())
    activity.begin_run(configuration(), generation=1)
    requested = requested_interaction()
    received = received_interaction()
    activity.append_interaction_update(requested)
    activity.append_event(
        event(1, "provider", "requested", llm_interaction_id="llm-0001")
    )
    activity.append_interaction_update(received)
    activity.append_event(
        event(2, "provider", "received", llm_interaction_id="llm-0001")
    )
    activity.complete_run(response(llm_interactions=[received]))

    assert json.loads(activity.export_json)["schema_version"] == "1.0.0"
    assert activity.include_full_transcript is False

    activity.include_full_transcript = True
    document = json.loads(activity.export_json)

    assert document["schema_version"] == "2.0.0"
    assert document["results"]["llm_interactions"] == [received]
    assert document["results"]["events"][0]["llm_interaction_id"] == "llm-0001"


def test_draft_settings_export_forces_transcript_choice_off() -> None:
    activity = load_activity().RunActivity()
    submitted = configuration()
    activity.set_draft_configuration(submitted)
    activity.begin_run(submitted, generation=1)
    activity.append_event(event(1, "run", "completed"))
    activity.complete_run(response())
    activity.include_full_transcript = True

    activity.set_draft_configuration({**submitted, "model": "draft-model"})
    activity.export_choice = "draft_settings_only"

    assert activity.include_full_transcript is False
    assert json.loads(activity.export_json)["results"] is None


def test_failed_run_can_prepare_stopped_v2_transcript() -> None:
    activity = load_activity().RunActivity()
    activity.set_draft_configuration(configuration())
    activity.begin_run(configuration(), generation=1)
    requested = requested_interaction()
    stopped = {
        **requested,
        "status": "stopped",
        "completed_at_utc": "2026-08-04T15:30:01.34Z",
        "safe_error": "The provider request stopped before completion.",
    }
    activity.append_interaction_update(requested)
    activity.append_event(
        event(1, "provider", "requested", llm_interaction_id="llm-0001")
    )
    activity.append_interaction_update(stopped)
    activity.fail_run("Analysis stopped before a safe result was available.")

    activity.include_full_transcript = True
    document = json.loads(activity.export_json)

    assert document["schema_version"] == "2.0.0"
    assert document["results"]["llm_interactions"][0]["status"] == "stopped"


def test_activity_updates_existing_interaction_without_reordering() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration(), generation=1)
    activity.append_interaction_update(requested_interaction())
    activity.append_interaction_update(received_interaction())

    assert len(activity.interactions) == 1
    assert activity.interactions[0]["status"] == "received"


def test_activity_rejects_out_of_order_and_invalid_interaction_updates() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration(), generation=1)

    with pytest.raises(ValueError, match="contiguous"):
        activity.append_interaction_update(requested_interaction(id="llm-0002"))

    activity.append_interaction_update(requested_interaction())
    with pytest.raises(ValueError, match="immutable"):
        activity.append_interaction_update(received_interaction(model="changed-model"))

    assert len(activity.interactions) == 1
    assert activity.interactions[0]["status"] == "requested"


def test_new_generation_clears_interactions_and_transcript_choice() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration(), generation=1)
    activity.append_interaction_update(requested_interaction())
    activity.include_full_transcript = True

    activity.begin_run(configuration(model="qwen3.5:4b"), generation=2)

    assert activity.interactions == []
    assert activity.include_full_transcript is False


def test_failed_run_retains_observed_interactions() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration(), generation=1)
    activity.append_interaction_update(requested_interaction())

    activity.fail_run("Analysis stopped before a safe result was available.")

    assert activity.interactions[0]["status"] == "requested"


def test_activity_tracks_result_and_draft_drift() -> None:
    activity = load_activity().RunActivity(
        utcnow=lambda: datetime(2026, 8, 3, 22, 30, tzinfo=timezone.utc)
    )
    submitted = configuration()
    activity.set_draft_configuration(submitted)
    activity.begin_run(submitted)
    activity.append_event(event(1, "run", "started"))
    activity.complete_run(response())

    assert activity.state == "completed"
    assert activity.events[0]["sequence"] == 1
    assert activity.final_elapsed_ms == 43_082
    assert activity.draft_differs is False
    assert activity.has_results is True

    activity.set_draft_configuration({**submitted, "model": "qwen3.5:4b"})
    assert activity.draft_differs is True
    activity.set_draft_configuration(submitted)
    assert activity.draft_differs is False


def test_begin_run_clears_old_result_events_and_elapsed() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration())
    activity.append_event(event(1, "run", "started"))
    activity.complete_run(response())

    activity.begin_run(configuration(model="qwen3.5:4b"))

    assert activity.state == "running"
    assert activity.events == []
    assert activity.final_elapsed_ms == 0
    assert activity.has_results is False


def test_begin_run_is_idempotent_per_submitted_generation() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration(), generation=1)
    activity.append_event(event(1, "run", "started"))

    activity.begin_run(configuration(), generation=1)

    assert [item["sequence"] for item in activity.events] == [1]
    assert activity.state == "running"

    activity.begin_run(configuration(model="qwen3.5:4b"), generation=2)
    assert activity.events == []
    assert activity.submitted_configuration["model"] == "qwen3.5:4b"


def test_failed_run_retains_only_safe_receipt_and_events() -> None:
    times = iter(
        (
            datetime(2026, 8, 3, 22, 24, 18, 270_000, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 22, 24, 20, 350_000, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 22, 24, 20, 350_000, tzinfo=timezone.utc),
        )
    )
    activity = load_activity().RunActivity(utcnow=lambda: next(times))
    activity.begin_run(configuration(), generation=1)
    activity.append_event(event(1, "run", "started"))

    activity.fail_run("Analysis stopped before a safe result was available.")

    assert activity.state == "failed"
    assert activity.has_results is True
    assert activity.final_elapsed_ms == 2_080
    assert activity.events[-1]["status"] == "stopped"
    document = json.loads(activity.export_json)
    assert document["results"]["run_receipt"]["status"] == "failed"
    assert "secret" not in activity.export_json.lower()


def test_activity_rejects_duplicate_or_out_of_order_events() -> None:
    activity = load_activity().RunActivity()
    activity.begin_run(configuration())
    activity.append_event(event(1, "run", "started"))

    with pytest.raises(ValueError):
        activity.append_event(event(1, "facts", "started"))
    with pytest.raises(ValueError):
        activity.append_event(event(3, "facts", "started"))

    assert [item["sequence"] for item in activity.events] == [1]


def test_export_generation_uses_authoritative_result_or_draft_settings() -> None:
    activity = load_activity().RunActivity(
        utcnow=lambda: datetime(2026, 8, 3, 22, 30, tzinfo=timezone.utc)
    )
    submitted = configuration()
    activity.set_draft_configuration(submitted)
    activity.begin_run(submitted)
    activity.append_event(event(1, "run", "completed"))
    activity.complete_run(response())
    activity.set_draft_configuration({**submitted, "model": "qwen3.5:4b"})

    activity.export_choice = "original_with_results"
    activity.export_generation += 1
    original_document = json.loads(activity.export_json)

    assert original_document["configuration"]["model"] == "llama3:8b"
    assert original_document["results"]["response"]["record"] is not None
    assert activity.export_filename == ("reasoning-lab-car-wash-20260803T223000Z.json")
    assert activity.export_ready_generation == activity.export_generation

    activity.export_choice = "draft_settings_only"
    activity.export_generation += 1
    draft_document = json.loads(activity.export_json)

    assert draft_document["configuration"]["model"] == "qwen3.5:4b"
    assert draft_document["results"] is None


def test_export_payload_is_prepared_before_the_explicit_browser_click() -> None:
    """The browser must not wait for a server round-trip to start a download."""

    activity = load_activity().RunActivity(
        utcnow=lambda: datetime(2026, 8, 3, 22, 30, tzinfo=timezone.utc)
    )
    submitted = configuration()

    activity.set_draft_configuration(submitted)
    assert activity.prepared_export_choice == "original_with_results"
    assert json.loads(activity.export_json)["results"] is None

    activity.begin_run(submitted)
    activity.append_event(event(1, "run", "completed"))
    activity.complete_run(response())
    assert json.loads(activity.export_json)["results"]["response"]["record"] is not None

    activity.set_draft_configuration({**submitted, "model": "qwen3.5:4b"})
    activity.export_choice = "draft_settings_only"
    assert activity.prepared_export_choice == "draft_settings_only"
    prepared = json.loads(activity.export_json)
    assert prepared["configuration"]["model"] == "qwen3.5:4b"
    assert prepared["results"] is None

    activity.set_draft_configuration(submitted)
    assert activity.draft_differs is False
    assert activity.export_choice == "original_with_results"
    assert activity.prepared_export_choice == "original_with_results"
    assert json.loads(activity.export_json)["results"] is not None


def test_pre_run_export_is_settings_only_and_invalid_choice_fails_closed() -> None:
    activity = load_activity().RunActivity()
    activity.set_draft_configuration(configuration())

    activity.export_generation += 1

    assert json.loads(activity.export_json)["results"] is None

    activity.export_choice = "unknown"
    activity.export_generation += 1

    assert activity.export_json == ""
    assert activity.export_filename == ""
    assert activity.export_error


def test_browser_renderer_has_accessible_activity_and_local_json_download() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    assert 'document.createElement("details")' in source
    assert "Run Activity" in source
    assert "LLM Interactions" in source
    assert "Include Full LLM Transcript" in source
    assert (
        "Includes complete application prompts and provider-visible responses."
        in source
    )
    assert "textContent" in source
    assert 'setAttribute("aria-live", "polite")' in source
    assert "draft settings do not match" in source.lower()
    assert "Original settings + results" in source
    assert "Draft settings only" in source
    assert "new Blob" in source
    assert "URL.createObjectURL" in source
    assert "URL.revokeObjectURL" in source
    assert "activity-status" in css
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "API_KEY",
        "license_token",
        "innerHTML",
        "marked(",
    ):
        assert forbidden not in source


def test_browser_renderer_uses_a_single_fixed_state_split_surface() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    for expected in (
        "split-surface",
        "run-activity-pane",
        "llm-interactions-pane",
        "pane-separator",
        "aria-controls",
        "aria-expanded",
        "eventNodes = new Map()",
        "interactionNodes = new Map()",
    ):
        assert expected in source
    assert "grid-template-columns: 1fr 0.3rem 1.5fr" in css
    assert "grid-template-columns: 1fr 0.3rem 4fr" in css
    assert "@media (max-width: 760px)" in css
    assert "Metrics" not in source
    assert "Parameters" not in source


def test_browser_semantic_follow_centers_linked_pairs_without_scroll_percentages() -> (
    None
):
    source = JS_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    for expected in (
        "createFollowState",
        "nearestLinkedId",
        "selectInteraction",
        "highlightInteraction(state.activeInteractionId)",
        "latestLinkedEventId",
        'scrollIntoView({ block: "center"',
        "requestAnimationFrame",
        "ResizeObserver",
        "event.isTrusted",
        "jump-to-live",
        "unseen",
        "prefers-reduced-motion: reduce",
    ):
        assert expected in source or expected in css
    assert "scrollTop /" not in source
    assert "scrollHeight /" not in source
    assert '["interaction-click", "interaction-scroll", "resize"]' in source


def test_programmatic_smooth_scroll_stays_guarded_until_scroll_end() -> None:
    source = JS_PATH.read_text(encoding="utf-8")

    assert "createProgrammaticScrollGuard" in source
    assert "scrollGuard.noteScroll(viewport)" in source
    assert 'addEventListener("scrollend"' in source
    assert "scrollGuard.end(activityLive)" in source
    assert "scrollGuard.end(interactionsLive)" in source
    assert "programmaticScrollSource" not in source


def test_browser_keyboard_navigation_is_linked_only_and_locally_scoped() -> None:
    source = JS_PATH.read_text(encoding="utf-8")

    assert 'event.key === "ArrowDown"' in source
    assert 'event.key === "ArrowUp"' in source
    assert "nextLinkedInteractionId" in source
    assert 'splitSurface.addEventListener("keydown"' in source
    assert 'window.addEventListener("keydown"' not in source
    assert 'document.addEventListener("keydown"' not in source
    assert 'event.key === "j"' not in source.lower()
    assert 'event.key === "k"' not in source.lower()


def test_browser_analyze_opens_interactions_without_overriding_manual_collapse() -> (
    None
):
    source = JS_PATH.read_text(encoding="utf-8")

    assert "paneStateOnAnalyze(media.matches)" in source
    assert 'previousModelState !== "running"' in source
    assert 'modelState === "running"' in source
    assert "separator.addEventListener" in source


def test_activity_colors_distinguish_processing_from_response_decisions() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert (
        ".activity-status-started,\n"
        ".activity-status-requested,\n"
        ".activity-status-received,\n"
        ".activity-status-completed"
    ) in css
    assert ".activity-status-accepted" in css
    assert ".activity-status-rejected" in css
    neutral_rule = css.split(".activity-status-started,", 1)[1].split("}", 1)[0]
    accepted_rule = css.split(".activity-status-accepted", 1)[1].split("}", 1)[0]
    rejected_rule = css.split(".activity-status-rejected", 1)[1].split("}", 1)[0]
    assert "#64748b" in neutral_rule
    assert "#16835d" in accepted_rule
    assert "#c2413b" in rejected_rule


def test_activity_rows_wrap_semantic_fields_without_horizontal_overflow() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert '"time status link"' in css
    assert '"component component component"' in css
    assert '"message message message"' in css
    assert ".activity-time {\n  grid-area: time;" in css
    assert ".activity-message {\n  grid-area: message;" in css
    assert ".activity-component {\n  grid-area: component;" in css
    assert ".activity-llm-link,\n.activity-no-llm {\n  grid-area: link;" in css
    assert ".run-activity-live {\n  overflow-x: hidden;" in css


def test_browser_download_is_a_direct_anchor_with_a_prepared_payload() -> None:
    """The user's click must target the download link itself, without synthesis."""

    source = JS_PATH.read_text(encoding="utf-8")
    assert 'element("a", "export-button", "Export JSON")' in source
    assert "exportButton.href = currentExportUrl;" in source
    assert 'exportButton.download = model.get("export_filename");' in source
    assert "anchor.click()" not in source
    assert "currentExportUrl" in source
