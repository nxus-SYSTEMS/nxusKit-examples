"""Unit tests for the safe Reasoning Lab LLM-interaction contract."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("llm_interactions.py")


def load_interactions():
    spec = importlib.util.spec_from_file_location("csg_llm_interactions", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixed_clock() -> datetime:
    return datetime(2026, 8, 4, 15, 30, 0, 129_999, tzinfo=timezone.utc)


def context(module, **changes):
    values = {
        "phase": "initial_recommendation",
        "response_attempt": 1,
        "source": "live",
        "provider": "claude",
        "model": "claude-haiku-4-5",
    }
    values.update(changes)
    return module.LLMCallContext(**values)


def requested_snapshot(**changes):
    values = {
        "id": "llm-0001",
        "linked_event_ids": [],
        "response_attempt": 1,
        "phase": "initial_recommendation",
        "source": "live",
        "provider": "claude",
        "model": "claude-haiku-4-5",
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
    values.update(changes)
    return values


def test_recorder_emits_stable_requested_received_snapshots() -> None:
    module = load_interactions()
    updates = []
    recorder = module.LLMInteractionRecorder(sink=updates.append, utcnow=fixed_clock)

    interaction_id = recorder.begin(
        context(module),
        system_prompt="Answer directly.",
        user_prompt="Choose a safe route.",
    )
    recorder.link_event(interaction_id, "event-0002")
    recorder.complete(interaction_id, "Use the certified route.")

    assert interaction_id == "llm-0001"
    assert [item["status"] for item in updates] == [
        "requested",
        "requested",
        "received",
    ]
    assert updates[0]["requested_at_utc"] == "2026-08-04T15:30:00.12Z"
    assert updates[-1]["completed_at_utc"] == "2026-08-04T15:30:00.12Z"
    assert updates[-1]["linked_event_ids"] == ["event-0002"]
    assert updates[-1]["response_content"] == "Use the certified route."
    assert updates[-1]["messages"] == [
        {"role": "system", "content": "Answer directly."},
        {"role": "user", "content": "Choose a safe route."},
    ]


def test_snapshots_are_immutable_and_event_links_are_deduplicated() -> None:
    module = load_interactions()
    updates = []
    recorder = module.LLMInteractionRecorder(sink=updates.append, utcnow=fixed_clock)
    interaction_id = recorder.begin(
        context(module), system_prompt="System", user_prompt="User"
    )
    first = updates[0]

    recorder.link_event(interaction_id, "event-0001")
    recorder.link_event(interaction_id, "event-0001")
    recorder.complete(interaction_id, "Response")

    assert first["linked_event_ids"] == []
    assert first["status"] == "requested"
    assert updates[-1]["linked_event_ids"] == ["event-0001"]


def test_recorder_assigns_contiguous_ids_and_stops_with_safe_error() -> None:
    module = load_interactions()
    updates = []
    recorder = module.LLMInteractionRecorder(sink=updates.append, utcnow=fixed_clock)

    first = recorder.begin(context(module), system_prompt="S1", user_prompt="U1")
    recorder.stop(first, "Provider request stopped.")
    second = recorder.begin(
        context(module, phase="fact_extraction"),
        system_prompt="S2",
        user_prompt="U2",
    )

    assert (first, second) == ("llm-0001", "llm-0002")
    assert updates[-2]["status"] == "stopped"
    assert updates[-2]["response_content"] is None
    assert updates[-2]["safe_error"] == "Provider request stopped."


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("phase", "chain_of_thought", "phase is not allowlisted"),
        ("source", "provider_cache", "source is not allowlisted"),
        ("response_attempt", 0, "response attempt must be a positive integer"),
        ("provider", "", "provider must contain"),
        ("model", "model\nsecret", "model must contain"),
    ],
)
def test_recorder_rejects_invalid_context(field: str, value, message: str) -> None:
    module = load_interactions()
    recorder = module.LLMInteractionRecorder(utcnow=fixed_clock)

    with pytest.raises(ValueError, match=message):
        recorder.begin(
            context(module, **{field: value}),
            system_prompt="System",
            user_prompt="User",
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"id": "call-1"}, "ID must use llm-NNNN format"),
        ({"linked_event_ids": ["event-1"]}, "event ID must use event-NNNN format"),
        ({"linked_event_ids": ["event-0001", "event-0001"]}, "must be unique"),
        ({"status": "streaming"}, "status is not allowlisted"),
        ({"requested_at_utc": "2026-08-04T15:30:00.12"}, "UTC hundredths"),
        ({"completed_at_utc": "2026-08-04T15:30:00.12Z"}, "requested interaction"),
        (
            {
                "messages": [
                    {"role": "assistant", "content": "No"},
                    {"role": "user", "content": "User"},
                ]
            },
            "message role",
        ),
        ({"messages": [{"role": "system", "content": "Only one"}]}, "exactly"),
        ({"safe_error": "secret\nleak"}, "safe error must contain"),
    ],
)
def test_validator_rejects_invalid_snapshot_shapes(changes, message: str) -> None:
    module = load_interactions()

    with pytest.raises(ValueError, match=message):
        module.validate_interaction_snapshot(requested_snapshot(**changes))


def test_validator_accepts_multiline_plain_text_and_hostile_html_canaries() -> None:
    module = load_interactions()
    hostile = '<img src=x onerror="alert(1)">\n```html\n<script>x</script>\n```'
    raw = requested_snapshot(
        messages=[
            {"role": "system", "content": "Line one\nLine two"},
            {"role": "user", "content": hostile},
        ]
    )

    validated = module.validate_interaction_snapshot(raw)

    assert validated["messages"][1]["content"] == hostile


def test_content_bound_is_exactly_two_hundred_thousand_characters() -> None:
    module = load_interactions()

    validated = module.validate_interaction_snapshot(
        requested_snapshot(
            messages=[
                {"role": "system", "content": "S"},
                {"role": "user", "content": "x" * 200_000},
            ]
        )
    )
    assert len(validated["messages"][1]["content"]) == 200_000

    with pytest.raises(ValueError, match="200000"):
        module.validate_interaction_snapshot(
            requested_snapshot(
                messages=[
                    {"role": "system", "content": "S"},
                    {"role": "user", "content": "x" * 200_001},
                ]
            )
        )


def test_validator_rejects_invalid_transitions() -> None:
    module = load_interactions()
    previous = module.validate_interaction_snapshot(requested_snapshot())
    received = module.validate_interaction_snapshot(
        requested_snapshot(
            status="received",
            completed_at_utc="2026-08-04T15:30:00.13Z",
            response_content="Response",
        ),
        previous=previous,
    )

    with pytest.raises(ValueError, match="terminal interaction cannot change"):
        module.validate_interaction_snapshot(requested_snapshot(), previous=received)
    with pytest.raises(ValueError, match="immutable interaction field changed"):
        module.validate_interaction_snapshot(
            requested_snapshot(provider="openai"), previous=previous
        )


def test_prompt_delta_is_deterministic_and_preserves_literal_lines() -> None:
    module = load_interactions()

    assert module.prompt_delta(
        "Keep temperature safe.\nUse any route.",
        "Keep temperature safe.\nUse only a certified route.",
    ) == {
        "added": ["Use only a certified route."],
        "removed": ["Use any route."],
    }


def test_repair_and_measured_outcome_annotations_are_validated() -> None:
    module = load_interactions()
    updates = []
    recorder = module.LLMInteractionRecorder(sink=updates.append, utcnow=fixed_clock)
    interaction_id = recorder.begin(
        context(module, phase="repaired_recommendation", response_attempt=2),
        system_prompt="System",
        user_prompt="Repaired prompt",
    )
    recorder.annotate_repair(
        interaction_id,
        {
            "repair_attempt": 1,
            "triggering_engines": ["solver", "zen"],
            "blocking_finding_count": 2,
            "repair_instructions": ["Use only a certified route."],
            "prompt_delta": {"added": ["Certified only."], "removed": []},
        },
    )
    recorder.complete(interaction_id, "Repaired response")
    recorder.annotate_outcome(
        2,
        {
            "status": "rejected",
            "blocking_finding_count": 1,
            "previous_blocking_finding_count": 2,
            "delta": "decreased",
            "engines": [
                {"id": "solver", "status": "rejected", "blocking_finding_count": 1},
                {"id": "zen", "status": "accepted", "blocking_finding_count": 0},
            ],
        },
    )

    assert updates[-1]["repair_context"]["repair_attempt"] == 1
    assert updates[-1]["outcome"]["delta"] == "decreased"
    assert updates[-1]["outcome"]["engines"][0]["id"] == "solver"


@pytest.mark.parametrize(
    "outcome",
    [
        {
            "status": "maybe",
            "blocking_finding_count": 1,
            "previous_blocking_finding_count": 2,
            "delta": "decreased",
            "engines": [],
        },
        {
            "status": "rejected",
            "blocking_finding_count": 1,
            "previous_blocking_finding_count": 2,
            "delta": "improved",
            "engines": [],
        },
    ],
)
def test_outcome_rejects_unmeasured_or_nonfactual_values(outcome) -> None:
    module = load_interactions()
    recorder = module.LLMInteractionRecorder(utcnow=fixed_clock)
    recorder.begin(
        context(module), system_prompt="System", user_prompt="Initial prompt"
    )

    with pytest.raises(ValueError):
        recorder.annotate_outcome(1, outcome)


def test_outcome_requires_exactly_one_recommendation_interaction() -> None:
    module = load_interactions()
    recorder = module.LLMInteractionRecorder(utcnow=fixed_clock)
    recorder.begin(
        context(module, phase="fact_extraction"),
        system_prompt="System",
        user_prompt="Extract facts",
    )

    with pytest.raises(
        ValueError, match="response attempt must identify one recommendation"
    ):
        recorder.annotate_outcome(
            1,
            {
                "status": "not_evaluated",
                "blocking_finding_count": 0,
                "previous_blocking_finding_count": None,
                "delta": "not_comparable",
                "engines": [],
            },
        )


def test_validator_rejects_outcomes_on_nonrecommendation_interactions() -> None:
    module = load_interactions()

    with pytest.raises(ValueError, match="only valid for a received recommendation"):
        module.validate_interaction_snapshot(
            requested_snapshot(
                phase="fact_extraction",
                status="received",
                completed_at_utc="2026-08-04T15:30:00.13Z",
                response_content="Structured facts",
                outcome={
                    "status": "accepted",
                    "blocking_finding_count": 0,
                    "previous_blocking_finding_count": None,
                    "delta": "not_comparable",
                    "engines": [],
                },
            )
        )


def test_validator_rejects_repair_context_on_an_initial_recommendation() -> None:
    module = load_interactions()

    with pytest.raises(ValueError, match="only valid for a repaired recommendation"):
        module.validate_interaction_snapshot(
            requested_snapshot(
                repair_context={
                    "repair_attempt": 1,
                    "triggering_engines": ["solver"],
                    "blocking_finding_count": 1,
                    "repair_instructions": ["Use only a certified route."],
                    "prompt_delta": {"added": ["Certified only."], "removed": []},
                }
            )
        )


@pytest.mark.parametrize(
    ("status", "blocking_finding_count"),
    [("accepted", 1), ("rejected", 0)],
)
def test_outcome_status_must_match_blocking_findings(
    status: str, blocking_finding_count: int
) -> None:
    module = load_interactions()
    recorder = module.LLMInteractionRecorder(utcnow=fixed_clock)
    interaction_id = recorder.begin(
        context(module), system_prompt="System", user_prompt="Initial prompt"
    )
    recorder.complete(interaction_id, "Response")

    with pytest.raises(ValueError, match="status does not match"):
        recorder.annotate_outcome(
            1,
            {
                "status": status,
                "blocking_finding_count": blocking_finding_count,
                "previous_blocking_finding_count": None,
                "delta": "not_comparable",
                "engines": [],
            },
        )


def test_outcome_targets_received_fallback_not_stopped_live_attempt() -> None:
    module = load_interactions()
    updates = []
    recorder = module.LLMInteractionRecorder(sink=updates.append, utcnow=fixed_clock)
    live_id = recorder.begin(
        context(module, source="live"),
        system_prompt="System",
        user_prompt="Live prompt",
    )
    recorder.stop(live_id, "The provider request stopped before completion.")
    fixture_id = recorder.begin(
        context(module, source="fixture", provider="fixture", model="checked-in"),
        system_prompt="System",
        user_prompt="Fixture prompt",
    )
    recorder.complete(fixture_id, "Fixture response")

    recorder.annotate_outcome(
        1,
        {
            "status": "accepted",
            "blocking_finding_count": 0,
            "previous_blocking_finding_count": None,
            "delta": "not_comparable",
            "engines": [],
        },
    )

    latest = {}
    for update in updates:
        latest[update["id"]] = update
    assert "outcome" not in latest[live_id]
    assert latest[fixture_id]["outcome"]["status"] == "accepted"
