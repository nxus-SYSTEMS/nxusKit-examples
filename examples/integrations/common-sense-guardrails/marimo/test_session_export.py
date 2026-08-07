"""Tests for the versioned Reasoning Lab session export contract."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).with_name("session_export.py")
FRONTEND_CORE_PATH = Path(__file__).with_name("frontend_core.py")


def load_exporter():
    spec = importlib.util.spec_from_file_location("csg_session_export", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_frontend_core():
    spec = importlib.util.spec_from_file_location(
        "coupon_export_frontend_core", FRONTEND_CORE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configuration(**overrides):
    value = {
        "scenario": "car-wash",
        "mode": "fixture",
        "provider": None,
        "model": None,
        "mechanisms": ["solver", "clips", "clips"],
        "max_repair_attempts": 3,
    }
    value.update(overrides)
    return value


def safe_event() -> dict:
    return {
        "sequence": 1,
        "timestamp_utc": "2026-08-03T22:24:18.27Z",
        "category": "run",
        "status": "completed",
        "message": "Analysis completed.",
    }


def result_response(*, status: str = "completed") -> dict:
    return {
        "mode": "live",
        "record": {"schema_version": "1.0.0", "scenario": {"id": "car-wash"}},
        "run_receipt": {
            "started_at_utc": "2026-08-04T15:30:00.12Z",
            "completed_at_utc": "2026-08-04T15:30:01.34Z",
            "elapsed_ms": 1_220,
            "status": status,
        },
    }


def safe_received_interaction(**changes) -> dict:
    value = {
        "id": "llm-0001",
        "linked_event_ids": ["event-0001"],
        "response_attempt": 1,
        "phase": "initial_recommendation",
        "source": "live",
        "provider": "ollama",
        "model": "llama3:8b",
        "status": "received",
        "requested_at_utc": "2026-08-04T15:30:00.12Z",
        "completed_at_utc": "2026-08-04T15:30:01.34Z",
        "messages": [
            {"role": "system", "content": "Answer directly."},
            {"role": "user", "content": "Choose a safe route."},
        ],
        "response_content": "Use the certified route.",
        "safe_error": None,
    }
    value.update(changes)
    return value


def linked_event() -> dict:
    return safe_event() | {
        "id": "event-0001",
        "llm_interaction_id": "llm-0001",
    }


def test_default_export_remains_byte_shape_compatible_v1() -> None:
    module = load_exporter()

    document = module.build_session_document(
        configuration(mode="live", provider="ollama", model="llama3:8b"),
        response=result_response(),
        events=[linked_event()],
        llm_interactions=[safe_received_interaction()],
    )

    assert document["schema_version"] == "1.0.0"
    assert "llm_interactions" not in document["results"]
    assert "id" not in document["results"]["events"][0]
    assert "llm_interaction_id" not in document["results"]["events"][0]


def test_explicit_transcript_export_is_linked_v2() -> None:
    module = load_exporter()
    interaction = safe_received_interaction()

    document = module.build_session_document(
        configuration(mode="live", provider="ollama", model="llama3:8b"),
        response=result_response(),
        events=[linked_event()],
        llm_interactions=[interaction],
        include_full_transcript=True,
    )

    assert document["schema_version"] == "2.0.0"
    assert document["results"]["llm_interactions"] == [interaction]
    assert document["results"]["events"][0]["llm_interaction_id"] == "llm-0001"


def test_settings_only_export_cannot_enable_transcript() -> None:
    with pytest.raises(ValueError, match="results-bearing"):
        load_exporter().build_session_document(
            configuration(),
            llm_interactions=[safe_received_interaction()],
            include_full_transcript=True,
        )


def test_stopped_run_can_export_safe_stopped_interaction() -> None:
    stopped = safe_received_interaction(
        status="stopped",
        completed_at_utc="2026-08-04T15:30:01.34Z",
        response_content=None,
        safe_error="The provider request stopped before completion.",
    )

    document = load_exporter().build_session_document(
        configuration(mode="live", provider="ollama", model="llama3:8b"),
        response=result_response(status="failed"),
        events=[linked_event()],
        llm_interactions=[stopped],
        include_full_transcript=True,
    )

    assert document["results"]["llm_interactions"][0]["status"] == "stopped"
    assert document["results"]["llm_interactions"][0]["safe_error"] == (
        "The provider request stopped before completion."
    )


def test_claims_v2_export_has_an_empty_interaction_list() -> None:
    document = load_exporter().build_session_document(
        configuration(
            scenario="synthetic-claims-audit",
            mechanisms=["claims-audit"],
        ),
        response={
            **result_response(),
            "mode": "fixture",
            "record": {
                "schema_version": "1.0.0",
                "scenario": {"id": "synthetic-claims-audit"},
            },
        },
        events=[safe_event() | {"id": "event-0001"}],
        llm_interactions=[],
        include_full_transcript=True,
    )

    assert document["schema_version"] == "2.0.0"
    assert document["results"]["llm_interactions"] == []


def test_coupon_auto_export_preserves_safe_containment_receipt() -> None:
    frontend = load_frontend_core()
    exporter = load_exporter()
    submitted = configuration(
        scenario="coupon-stack",
        mode="auto",
        provider=None,
        model=None,
        mechanisms=["clips"],
    )
    response = frontend.analyze_request(
        submitted,
        submitted=True,
        provider_availability=[{"id": "claude", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )
    response["run_receipt"] = {
        "started_at_utc": "2026-08-06T12:00:00.00Z",
        "completed_at_utc": "2026-08-06T12:00:00.01Z",
        "elapsed_ms": 10,
        "status": "completed",
    }

    serialized = exporter.serialize_session_document(
        exporter.build_session_document(submitted, response=response)
    )
    payload = json.loads(serialized)

    assert payload["kind"] == "nxuskit.reasoning-lab-session"
    assert payload["schema_version"] == "1.0.0"
    assert serialized.endswith("\n")
    assert '\n  "configuration": {' in serialized
    assert payload["configuration"]["mode"] == "auto"
    exported_response = payload["results"]["response"]
    assert exported_response["mode"] == "auto"
    assert exported_response["execution"] == {
        "llm_source": "checked-in fixture",
        "provider_contacted": False,
        "resolved_mode": "mock",
        "compatibility_code": (
            "coupon_live_strict_schema_transport_unavailable_v1_0_5"
        ),
        "message": (
            "Coupon stack Auto uses checked-in fixtures with nxusKit v1.0.5 "
            "because the Python provider path cannot preserve the required strict "
            "schema; no provider was contacted."
        ),
    }
    provenance = exported_response["record"]["provenance"]
    assert provenance["mode"] == "fixture"
    assert "resolved_mode" not in provenance
    assert "provider_contacted" not in provenance
    assert "compatibility_code" not in provenance
    assert exported_response["requested_provider"] is None
    assert exported_response["requested_model"] is None


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "credential",
        "headers",
        "environment",
        "license_claims",
        "hidden_reasoning",
        "raw_error_body",
        "metrics",
        "parameters",
    ],
)
def test_v2_transcript_rejects_noncontract_or_sensitive_fields(
    forbidden_field: str,
) -> None:
    interaction = safe_received_interaction()
    interaction[forbidden_field] = "SECRET_CANARY"

    with pytest.raises(ValueError):
        load_exporter().build_session_document(
            configuration(mode="live", provider="ollama", model="llama3:8b"),
            response=result_response(),
            events=[linked_event()],
            llm_interactions=[interaction],
            include_full_transcript=True,
        )


def test_settings_only_export_has_one_normalized_configuration() -> None:
    module = load_exporter()
    document = module.build_session_document(
        configuration(),
        exported_at=datetime(2026, 8, 3, 22, 30, 0, 129_999, tzinfo=timezone.utc),
    )

    assert document == {
        "kind": "nxuskit.reasoning-lab-session",
        "schema_version": "1.0.0",
        "exported_at_utc": "2026-08-03T22:30:00.12Z",
        "configuration": {
            "scenario": "car-wash",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "reasoning_engines": ["clips", "solver"],
            "max_repair_attempts": 3,
        },
        "results": None,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"scenario": "unknown"},
        {"mode": "mock"},
        {"provider": 123},
        {"model": ["not-a-model"]},
        {"mechanisms": ["clips", "unknown"]},
        {"max_repair_attempts": 0},
        {"max_repair_attempts": 11},
    ],
)
def test_configuration_validation_fails_closed(overrides: dict) -> None:
    with pytest.raises(ValueError):
        load_exporter().normalize_configuration(configuration(**overrides))


def test_result_export_allowlists_response_receipt_and_events() -> None:
    module = load_exporter()
    response = {
        "mode": "live",
        "record": {"schema_version": "1.0.0", "scenario": {"id": "car-wash"}},
        "execution": {
            "llm_source": "nxusKit provider",
            "provider_contacted": True,
            "message": "The selected provider and model were invoked through nxusKit.",
        },
        "effective_guardrails": ["clips", "solver"],
        "skipped_mechanisms": [],
        "requested_provider": "ollama",
        "requested_model": "llama3:8b",
        "message": "Record built after explicit Analyze selection.",
        "run_receipt": {
            "started_at_utc": "2026-08-03T22:24:18.27Z",
            "completed_at_utc": "2026-08-03T22:25:01.35Z",
            "elapsed_ms": 43082,
            "status": "completed",
        },
        "pro_availability": [{"license_token": "SECRET_CANARY"}],
        "credential": "SECRET_CANARY",
        "license_token": "SECRET_CANARY",
        "debug": "SECRET_CANARY",
    }

    document = module.build_session_document(
        configuration(
            mode="live",
            provider="ollama",
            model="llama3:8b",
            mechanisms=["clips", "solver"],
        ),
        response=response,
        events=[safe_event()],
        exported_at=datetime(2026, 8, 3, 22, 30, tzinfo=timezone.utc),
    )
    encoded = module.serialize_session_document(document)

    assert set(document["results"]) == {"response", "run_receipt", "events"}
    assert document["results"]["response"]["record"] == response["record"]
    assert document["results"]["run_receipt"]["elapsed_ms"] == 43082
    assert document["results"]["events"] == [safe_event()]
    assert "SECRET_CANARY" not in encoded
    assert "pro_availability" not in encoded
    assert "credential" not in encoded
    assert "license_token" not in encoded


def test_result_export_preserves_safe_processing_and_decision_statuses() -> None:
    module = load_exporter()
    statuses = ["requested", "received", "accepted", "rejected"]
    events = [
        {
            "sequence": index,
            "timestamp_utc": f"2026-08-03T22:24:{17 + index:02d}.27Z",
            "category": "run",
            "status": status,
            "message": f"Safe {status} event.",
        }
        for index, status in enumerate(statuses, start=1)
    ]
    response = {
        "mode": "fixture",
        "record": {"schema_version": "1.0.0", "scenario": {"id": "car-wash"}},
        "run_receipt": {
            "started_at_utc": "2026-08-03T22:24:18.27Z",
            "completed_at_utc": "2026-08-03T22:24:22.27Z",
            "elapsed_ms": 4000,
            "status": "completed",
        },
    }

    document = module.build_session_document(
        configuration(), response=response, events=events
    )

    assert document["results"]["events"] == events


def test_result_export_rejects_unknown_event_status() -> None:
    event = safe_event()
    event["status"] = "unknown"
    response = {
        "mode": "fixture",
        "record": {"schema_version": "1.0.0", "scenario": {"id": "car-wash"}},
        "run_receipt": {
            "started_at_utc": "2026-08-03T22:24:18.27Z",
            "completed_at_utc": "2026-08-03T22:24:19.27Z",
            "elapsed_ms": 1000,
            "status": "completed",
        },
    }

    with pytest.raises(ValueError, match="event status is invalid"):
        load_exporter().build_session_document(
            configuration(), response=response, events=[event]
        )


def test_failed_analysis_remains_exportable_without_a_record() -> None:
    module = load_exporter()
    response = {
        "mode": "live",
        "record": None,
        "message": "Live analysis could not validate the structured result.",
        "run_receipt": {
            "started_at_utc": "2026-08-03T22:24:18.27Z",
            "completed_at_utc": "2026-08-03T22:24:20.27Z",
            "elapsed_ms": 2000,
            "status": "failed",
        },
    }

    document = module.build_session_document(
        configuration(mode="live", provider="ollama", model="llama3:8b"),
        response=response,
        events=[safe_event()],
    )

    assert document["results"]["response"] == {
        "mode": "live",
        "record": None,
        "message": "Live analysis could not validate the structured result.",
    }
    assert document["results"]["run_receipt"]["status"] == "failed"


def test_serialization_and_filename_are_deterministic_and_human_readable() -> None:
    module = load_exporter()
    exported_at = datetime(2026, 8, 3, 22, 30, 0, tzinfo=timezone.utc)
    document = module.build_session_document(configuration(), exported_at=exported_at)

    encoded = module.serialize_session_document(document)

    assert encoded.endswith("\n")
    assert json.loads(encoded) == document
    assert module.export_filename("car-wash", exported_at) == (
        "reasoning-lab-car-wash-20260803T223000Z.json"
    )


def test_configurations_match_after_normalization() -> None:
    module = load_exporter()

    assert module.configurations_match(
        configuration(mechanisms=["solver", "clips"]),
        configuration(mechanisms=["clips", "solver", "clips"]),
    )
