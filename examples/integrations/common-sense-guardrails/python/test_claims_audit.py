"""Tests for the synthetic administrative claims-audit example surface."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from claims_audit import (
    ClaimsDataError,
    audit_claim_lines,
    build_claims_reasoning_record,
    generate_claim_csv,
    load_claims_fixture,
    load_optional_local_compatible_claims,
    profile_row_count,
    validate_claims_payload,
)
from claims_polars import claims_lazy_summary, claims_observational_sql


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "synthetic-claims-audit.schema.json"
RECORD_SCHEMA = ROOT / "schemas" / "reasoning-record.schema.json"


def test_tiny_fixture_is_synthetic_and_audit_is_structural() -> None:
    payload = load_claims_fixture()
    assert payload["synthetic"] is True
    assert payload["claim_lines"]
    findings = audit_claim_lines(payload["claim_lines"])
    rule_ids = {finding["rule_id"] for finding in findings}
    assert {
        "duplicate-synthetic-line-key",
        "missing-evidence-link",
        "invalid-date-order",
        "service-window-mismatch",
        "negative-or-implausible-amount",
        "missing-synthetic-service-reference",
        "missing-synthetic-provider-reference",
    } <= rule_ids
    assert all(finding["tier"] == "community" for finding in findings)
    assert all(
        "expert-review audit" in finding["message"].lower() for finding in findings
    )


def test_fixture_schema_and_canonical_record_validate() -> None:
    payload = load_claims_fixture()
    jsonschema.validate(payload, json.loads(SCHEMA.read_text()))
    record = build_claims_reasoning_record()
    jsonschema.validate(record, json.loads(RECORD_SCHEMA.read_text()))
    assert record["scenario"]["id"] == "synthetic-claims-audit"
    assert record["provenance"]["mode"] == "fixture"
    assert record["final"]["review_disposition"] == "review_required"


def test_pii_shaped_fields_and_unbounded_profiles_fail_closed(tmp_path: Path) -> None:
    payload = load_claims_fixture()
    payload["claim_lines"][0]["patient_name"] = "not-allowed"
    with pytest.raises(ClaimsDataError, match="PII-shaped"):
        validate_claims_payload(payload)

    payload = load_claims_fixture()
    payload["claim_lines"][0]["diagnosis"] = "not-allowed"
    with pytest.raises(ClaimsDataError, match="prohibited wording"):
        validate_claims_payload(payload)

    with pytest.raises(ClaimsDataError, match="bounded profile"):
        profile_row_count("2m")
    with pytest.raises(ClaimsDataError, match="bounded profile"):
        generate_claim_csv(tmp_path / "too-large.csv", rows=1_000_001, seed=7)


def test_optional_local_adapter_requires_an_explicit_compatible_selection(
    tmp_path: Path,
) -> None:
    source = tmp_path / "local.csv"
    source.write_text(
        "line_key,service_ref,synthetic\nsynthetic-line,synthetic-service,true\n"
    )
    with pytest.raises(ClaimsDataError, match="source_kind"):
        load_optional_local_compatible_claims(source, "unselected")
    assert load_optional_local_compatible_claims(source, "cms-synpuf") == [
        {
            "line_key": "synthetic-line",
            "service_ref": "synthetic-service",
            "synthetic": "true",
        }
    ]


def test_seeded_expansion_and_polars_lazy_streaming_proof(tmp_path: Path) -> None:
    first = generate_claim_csv(tmp_path / "first.csv", profile="1k", seed=20260729)
    second = generate_claim_csv(tmp_path / "second.csv", profile="1k", seed=20260729)
    assert profile_row_count("1k") == 1_000
    assert (
        hashlib.sha256(first.read_bytes()).hexdigest()
        == hashlib.sha256(second.read_bytes()).hexdigest()
    )

    summary = claims_lazy_summary(first)
    assert summary["row_count"] == 1_000
    assert "SCAN" in summary["query_plan"].upper()
    assert summary["streaming_engine"] == "streaming"
    sql = claims_observational_sql(summary["materialized"])
    assert sql["row_count"] == 1_000
