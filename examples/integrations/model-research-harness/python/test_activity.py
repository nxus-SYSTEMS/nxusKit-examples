"""Contract tests for allowlisted Model Research activity projections."""

from __future__ import annotations

import pytest

from harness.activity import EvaluationTrace
from harness import providers
from harness.providers import ProviderError
from harness.runner import run_config


FIXED_TIME = "2026-08-07T20:00:00.000Z"


def new_trace():
    events: list[dict[str, object]] = []
    interactions: list[dict[str, object]] = []
    return (
        EvaluationTrace(events.append, interactions.append, clock=lambda: FIXED_TIME),
        events,
        interactions,
    )


def fixture_config() -> dict[str, object]:
    return {
        "id": "trace-fixture",
        "providers": [
            {
                "id": "local-fixture",
                "provider": "loopback",
                "model": "fixture-json-v1",
            }
        ],
        "tests": [
            {
                "id": "schema-validated-output",
                "prompt": "Return JSON for {{ ticket }}",
                "vars": {"ticket": "a synthetic support ticket"},
                "provider_ids": ["local-fixture"],
                "mock_response": {"label": "technical"},
                "assertions": [{"type": "is-json"}],
            }
        ],
    }


def test_run_config_without_trace_preserves_report_inputs() -> None:
    """Catches instrumentation changing canonical runner output."""

    config = fixture_config()
    baseline = run_config(config, mode="mock")
    traced = run_config(config, mode="mock", trace=EvaluationTrace())

    assert traced == baseline


def test_fixture_trace_orders_canonical_evaluation_boundaries() -> None:
    """Catches reordered or duplicate model, scoring, or aggregation evidence."""

    trace, events, interactions = new_trace()

    run_config(fixture_config(), mode="mock", trace=trace)

    assert [event["phase"] for event in events] == [
        "model_request",
        "model_response",
        "parse",
        "assertion",
        "policy",
        "bayesian",
    ]
    assert interactions[-1]["status"] == "evaluated"
    assert interactions[-1]["assertions"][0]["status"] == "pass"


def test_live_request_snapshot_precedes_provider_invocation(monkeypatch) -> None:
    """Catches Live evidence appearing only after a blocking provider call."""

    trace, events, interactions = new_trace()
    observed: list[str] = []

    def fake_live_provider(*_args, **_kwargs):
        assert interactions[-1]["status"] == "requested"
        assert events[-1]["phase"] == "model_request"
        observed.append("provider-called")
        return {
            "content": '{"label":"technical"}',
            "source": "live",
            "provider_id": "claude",
            "model": "claude-sonnet-4-6",
            "metadata": {},
        }

    monkeypatch.setattr(providers, "call_live_provider", fake_live_provider)
    response = providers.call_provider(
        fixture_config()["providers"][0],
        fixture_config()["tests"][0],
        "live",
        provider_override="claude",
        model_override="claude-sonnet-4-6",
        trace=trace,
    )

    assert observed == ["provider-called"]
    assert response["source"] == "live"
    assert interactions[-1]["status"] == "received"


def test_live_provider_error_preserves_safe_partial_evidence(monkeypatch) -> None:
    """Catches provider secrets leaking or requested evidence disappearing on error."""

    canary = "must-not-leak-provider-canary"
    trace, events, interactions = new_trace()

    def fail_live_provider(*_args, **_kwargs):
        raise ProviderError(f"provider rejected {canary}")

    monkeypatch.setattr(providers, "call_live_provider", fail_live_provider)

    with pytest.raises(ProviderError, match="provider rejected"):
        providers.call_provider(
            fixture_config()["providers"][0],
            fixture_config()["tests"][0],
            "live",
            provider_override="claude",
            model_override="claude-sonnet-4-6",
            trace=trace,
        )

    assert interactions[-1]["status"] == "error"
    assert interactions[-1]["error"] == "Provider interaction failed."
    assert canary not in str(events)
    assert canary not in str(interactions)


def test_trace_emits_contiguous_linked_fixture_evidence() -> None:
    """Catches gaps, mismatched links, or false provider provenance."""

    trace, events, interactions = new_trace()
    interaction_id = trace.begin_interaction(
        test_id="schema-validated-output",
        source="fixture",
        provider="json-fixture",
        model="fixture-json-v1",
        system_prompt=None,
        user_prompt="Return JSON",
    )
    trace.receive_interaction(interaction_id, response_content='{"label":"technical"}')

    assert interaction_id == "interaction-0001"
    assert [event["id"] for event in events] == ["event-0001", "event-0002"]
    assert interactions[-1]["provenance_label"] == (
        "Fixture Response — No Provider Contacted"
    )
    assert interactions[-1]["linked_event_ids"] == ["event-0001", "event-0002"]
    assert interactions[-1]["status"] == "received"


def test_sink_snapshots_are_deep_copies_of_internal_state() -> None:
    """Catches later updates or consumer mutation rewriting earlier evidence."""

    trace, _events, interactions = new_trace()
    interaction_id = trace.begin_interaction(
        test_id="ticket",
        source="fixture",
        provider="fixture-provider",
        model="fixture-model",
        system_prompt=None,
        user_prompt="Classify ticket",
    )
    requested = interactions[0]
    requested["status"] = "corrupted"
    requested["linked_event_ids"].append("event-9999")

    trace.receive_interaction(interaction_id, response_content="{}")

    assert interactions[-1]["status"] == "received"
    assert interactions[-1]["linked_event_ids"] == ["event-0001", "event-0002"]


@pytest.mark.parametrize(
    "forbidden",
    [
        "api_key",
        "authorization",
        "headers",
        "environment",
        "license_token",
        "credential",
    ],
)
def test_forbidden_fields_fail_before_reaching_a_sink(forbidden: str) -> None:
    """Catches credential-bearing fields crossing into synchronized UI evidence."""

    trace, events, interactions = new_trace()

    with pytest.raises(ValueError, match="forbidden trace field"):
        trace.event(
            phase="configuration",
            status="started",
            summary="Loading config",
            **{forbidden: "must-not-emit"},
        )

    assert events == []
    assert interactions == []


def test_caller_cannot_inject_ids_or_unknown_fields() -> None:
    """Catches duplicate or noncontiguous caller-controlled evidence identities."""

    trace, events, _interactions = new_trace()

    with pytest.raises(ValueError, match="unsupported trace field"):
        trace.event(
            phase="configuration",
            status="started",
            summary="Loading config",
            id="event-0009",
        )
    with pytest.raises(ValueError, match="unsupported trace field"):
        trace.begin_interaction(
            test_id="ticket",
            source="fixture",
            provider="fixture-provider",
            model="fixture-model",
            system_prompt=None,
            user_prompt="Classify",
            interaction_id="interaction-0009",
        )

    assert events == []


def test_invalid_status_and_unknown_interaction_fail_closed() -> None:
    """Catches ambiguous statuses or updates to nonexistent interactions."""

    trace, events, interactions = new_trace()

    with pytest.raises(ValueError, match="unsupported event status"):
        trace.event(
            phase="configuration",
            status="maybe",
            summary="Ambiguous state",
        )
    with pytest.raises(ValueError, match="unknown interaction"):
        trace.receive_interaction("interaction-9999", response_content="{}")
    with pytest.raises(ValueError, match="unknown interaction"):
        trace.fail_interaction("interaction-9999", error_message="failed")
    with pytest.raises(ValueError, match="unknown interaction"):
        trace.evaluate_interaction(
            "interaction-9999",
            parsed={},
            parse_error=None,
            assertions=[],
            policy={},
        )

    assert events == []
    assert interactions == []


def test_evaluated_interaction_preserves_allowlisted_result_details() -> None:
    """Catches parse, assertion, or policy evidence disappearing from the trace."""

    trace, events, interactions = new_trace()
    interaction_id = trace.begin_interaction(
        test_id="schema-validated-output",
        source="live",
        provider="ollama",
        model="qwen3.5:4b",
        system_prompt="Return safe JSON.",
        user_prompt="Classify synthetic ticket.",
    )
    trace.receive_interaction(
        interaction_id,
        response_content='{"label":"technical","confidence":0.9}',
    )
    trace.evaluate_interaction(
        interaction_id,
        parsed={"label": "technical", "confidence": 0.9},
        parse_error=None,
        assertions=[{"type": "is-json", "status": "pass", "detail": "valid JSON"}],
        policy={"status": "pass", "findings": []},
    )

    assert [event["id"] for event in events] == [
        f"event-{number:04d}" for number in range(1, len(events) + 1)
    ]
    assert interactions[-1]["status"] == "evaluated"
    assert interactions[-1]["parsed"] == {"label": "technical", "confidence": 0.9}
    assert interactions[-1]["assertions"] == [
        {"type": "is-json", "status": "pass", "detail": "valid JSON"}
    ]
    assert interactions[-1]["policy"] == {"status": "pass", "findings": []}
    assert interactions[-1]["linked_event_ids"] == [event["id"] for event in events]


def test_provider_failure_emits_only_a_safe_error_summary() -> None:
    """Catches provider exception contents leaking through a partial trace."""

    trace, events, interactions = new_trace()
    interaction_id = trace.begin_interaction(
        test_id="ticket",
        source="live",
        provider="claude",
        model="claude-sonnet-4-6",
        system_prompt=None,
        user_prompt="Classify synthetic ticket.",
    )
    trace.fail_interaction(
        interaction_id,
        error_message="Authorization failed for must-not-leak-secret-canary",
    )

    assert interactions[-1]["status"] == "error"
    assert interactions[-1]["error"] == "Provider interaction failed."
    assert "must-not-leak-secret-canary" not in str(events)
    assert "must-not-leak-secret-canary" not in str(interactions)
