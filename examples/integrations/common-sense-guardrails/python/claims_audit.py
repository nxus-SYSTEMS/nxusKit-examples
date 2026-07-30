"""Offline synthetic administrative-data quality and evidence audit helpers.

The module deliberately accepts only marked synthetic rows.  Its results are
structural review findings, not external determinations, and it does not make
provider, network, filesystem-discovery, or nxusKit runtime calls.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from guardrail_core import reasoning_record_from_report


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "scenarios" / "synthetic-claims-audit" / "fixture.json"
PROFILE_ROWS = {"1k": 1_000, "100k": 100_000, "1m": 1_000_000}
MAX_SYNTHETIC_ROWS = max(PROFILE_ROWS.values())
PII_SHAPED_FIELD_TOKENS = (
    "patient",
    "person",
    "name",
    "email",
    "phone",
    "address",
    "ssn",
    "identifier",
)
PROHIBITED_ASSERTION_TOKENS = (
    "diagnosis",
    "treatment",
    "medical_necessity",
    "benefit",
    "payment",
    "reimbursement",
    "fraud",
    "hipaa",
    "de-identification",
)
CSV_FIELDS = (
    "line_key",
    "claim_key",
    "service_ref",
    "provider_ref",
    "evidence_refs",
    "service_start",
    "service_end",
    "service_window_start",
    "service_window_end",
    "recorded_amount_cents",
    "synthetic",
)


class ClaimsDataError(ValueError):
    """Raised when a fixture or scale request crosses this example boundary."""


def _assert_no_pii_shaped_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(token in normalized for token in PII_SHAPED_FIELD_TOKENS):
                raise ClaimsDataError(f"PII-shaped field is not allowed: {key}")
            if any(token in normalized for token in PROHIBITED_ASSERTION_TOKENS):
                raise ClaimsDataError(f"prohibited wording is not allowed: {key}")
            _assert_no_pii_shaped_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_pii_shaped_fields(nested)


def validate_claims_payload(payload: dict[str, Any]) -> None:
    """Fail closed unless the incoming data is bounded, structured, synthetic."""

    _assert_no_pii_shaped_fields(payload)
    if payload.get("synthetic") is not True:
        raise ClaimsDataError("synthetic marker is required")
    lines = payload.get("claim_lines")
    if not isinstance(lines, list) or not lines:
        raise ClaimsDataError("claim_lines must be a non-empty list")
    if len(lines) > MAX_SYNTHETIC_ROWS:
        raise ClaimsDataError("bounded profile permits at most 1m synthetic rows")
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict) or line.get("synthetic") is not True:
            raise ClaimsDataError(f"synthetic marker is required on line {index}")
        missing = [field for field in CSV_FIELDS if field not in line]
        if missing:
            raise ClaimsDataError(f"line {index} missing fields: {', '.join(missing)}")


def load_claims_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    """Load the checked-in tiny fixture without downloading or discovering data."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ClaimsDataError(f"missing synthetic fixture: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ClaimsDataError(f"invalid synthetic fixture JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClaimsDataError("synthetic fixture must be an object")
    validate_claims_payload(payload)
    return payload


def _finding(rule_id: str, line: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "tier": "community",
        "status": "warn",
        "severity": "warning",
        "message": f"Synthetic administrative expert-review audit: {message}",
        "repair_hint": "Resolve the structural reference or value, then rerun this synthetic review example.",
        "evidence": {
            "line_key": str(line.get("line_key", "")),
            "claim_key": str(line.get("claim_key", "")),
            "runtime_executed": False,
        },
    }


def audit_claim_lines(lines: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic structural findings for synthetic administrative rows."""

    findings: list[dict[str, Any]] = []
    seen_line_keys: set[str] = set()
    for line in lines:
        line_key = str(line.get("line_key", ""))
        if line_key in seen_line_keys:
            findings.append(
                _finding(
                    "duplicate-synthetic-line-key",
                    line,
                    "duplicate synthetic line key requires a data-quality review.",
                )
            )
        seen_line_keys.add(line_key)
        if not line.get("evidence_refs"):
            findings.append(
                _finding(
                    "missing-evidence-link",
                    line,
                    "missing evidence link requires an evidence-completeness review.",
                )
            )
        if str(line.get("service_end", "")) < str(line.get("service_start", "")):
            findings.append(
                _finding(
                    "invalid-date-order",
                    line,
                    "service end precedes service start and requires a structural review.",
                )
            )
        service_start = str(line.get("service_start", ""))
        if not (
            str(line.get("service_window_start", ""))
            <= service_start
            <= str(line.get("service_window_end", ""))
        ):
            findings.append(
                _finding(
                    "service-window-mismatch",
                    line,
                    "service date is outside its declared synthetic window.",
                )
            )
        if (
            not isinstance(line.get("recorded_amount_cents"), int)
            or line["recorded_amount_cents"] < 0
        ):
            findings.append(
                _finding(
                    "negative-or-implausible-amount",
                    line,
                    "recorded amount is negative or not an integer value.",
                )
            )
        if not str(line.get("service_ref", "")).strip():
            findings.append(
                _finding(
                    "missing-synthetic-service-reference",
                    line,
                    "a synthetic service reference is missing.",
                )
            )
        if not str(line.get("provider_ref", "")).strip():
            findings.append(
                _finding(
                    "missing-synthetic-provider-reference",
                    line,
                    "a synthetic provider reference is missing.",
                )
            )
    return findings


def build_claims_reasoning_record() -> dict[str, Any]:
    """Build the shared canonical record from the offline Community audit."""

    payload = load_claims_fixture()
    findings = audit_claim_lines(payload["claim_lines"])
    report = {
        "example": "common-sense-guardrails",
        "scenario": "synthetic-claims-audit",
        "mode": "mock",
        "resolved_mode": "mock",
        "requested_stage": "claims-audit",
        "requested_guardrails": "claims-audit",
        "guardrail_selection": {"selected": ["claims-audit"]},
        "max_repair_attempts": 1,
        "stages": [
            {
                "id": "structured-facts",
                "source": "mock",
                "output": {
                    "current": {
                        "synthetic_line_count": len(payload["claim_lines"]),
                        "structural_finding_count": len(findings),
                        "confidence": 1.0,
                    },
                    "attempts": [{"attempt": 1, "status": "warn"}],
                },
            },
            {
                "id": "claims-audit",
                "tier": "community",
                "source": "mock",
                "output": {
                    "mechanism": "claims-audit",
                    "attempts": [{"attempt": 1, "findings": findings}],
                },
            },
        ],
        "final_status": "warn",
        "summary": "Synthetic administrative expert-review audit has structural data-quality and evidence-completeness findings.",
    }
    return reasoning_record_from_report(report)


def profile_row_count(profile: str) -> int:
    """Return one explicit, bounded deterministic expansion size."""

    try:
        return PROFILE_ROWS[profile]
    except KeyError as exc:
        raise ClaimsDataError("bounded profile must be one of 1k, 100k, or 1m") from exc


def _row_count(profile: str | None, rows: int | None) -> int:
    if (profile is None) == (rows is None):
        raise ClaimsDataError("select exactly one bounded profile or row count")
    count = profile_row_count(profile) if profile is not None else rows
    if not isinstance(count, int) or not 1 <= count <= MAX_SYNTHETIC_ROWS:
        raise ClaimsDataError("bounded profile permits 1 through 1m synthetic rows")
    return count


def generate_claim_csv(
    path: Path, *, profile: str | None = None, rows: int | None = None, seed: int = 0
) -> Path:
    """Create a deterministic, local-only synthetic CSV expansion at a bounded size."""

    count = _row_count(profile, rows)
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for index in range(count):
            offset = rng.randrange(28)
            service_day = start + timedelta(days=offset)
            writer.writerow(
                {
                    "line_key": f"generated-line-{index:07d}",
                    "claim_key": f"generated-claim-{index:07d}",
                    "service_ref": f"generated-service-{index % 97:03d}",
                    "provider_ref": f"generated-provider-{index % 23:03d}",
                    "evidence_refs": f"generated-evidence-{index:07d}",
                    "service_start": service_day.isoformat(),
                    "service_end": service_day.isoformat(),
                    "service_window_start": start.isoformat(),
                    "service_window_end": "2026-01-28",
                    "recorded_amount_cents": 1000 + (index % 250),
                    "synthetic": "true",
                }
            )
    return path


def load_optional_local_compatible_claims(
    path: Path, source_kind: str
) -> list[dict[str, str]]:
    """Read an explicitly selected local, synthetic-compatible CSV mapping only.

    This adapter has no downloader or remote lookup. Callers must first make
    the source local and ensure it contains no PII-shaped columns.
    """

    if source_kind not in {"cms-synpuf", "synthea-derived"}:
        raise ClaimsDataError("source_kind must be cms-synpuf or synthea-derived")
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError as exc:
        raise ClaimsDataError(f"selected local source is unavailable: {path}") from exc
    _assert_no_pii_shaped_fields(rows)
    if len(rows) > MAX_SYNTHETIC_ROWS:
        raise ClaimsDataError("bounded profile permits at most 1m local rows")
    if any(str(row.get("synthetic", "")).lower() != "true" for row in rows):
        raise ClaimsDataError("selected local rows must carry a synthetic=true marker")
    return rows
