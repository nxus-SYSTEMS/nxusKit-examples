"""Pure canonical reasoning-record conversion for common-sense guardrails.

This module deliberately accepts an already-produced structured report. It has
no CLI parsing, provider setup, environment lookup, filesystem access, or
native-session side effect, so ordinary Python frontends can share one
inspectable record without becoming a second behavioral authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


REASONING_RECORD_VERSION = "1.0.0"
SDK_VERSION = "1.0.5"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _identifier(prefix: str, value: str) -> str:
    normalized = "".join(
        char.lower() if char.isalnum() else "-" for char in value
    ).strip("-")
    return f"{prefix}-{normalized or 'item'}"


def _record_source(value: str | None) -> str:
    return "local_runtime" if value == "live" else "fixture"


def _availability(source: str) -> str:
    return "available" if source == "local_runtime" else "fixture"


def _runtime_executed(finding: dict[str, Any]) -> bool:
    evidence = finding.get("evidence")
    return bool(isinstance(evidence, dict) and evidence.get("runtime_executed"))


def _mechanism_stages(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        stage
        for stage in report.get("stages", [])
        if isinstance(stage.get("output"), dict)
        and isinstance(stage["output"].get("mechanism"), str)
    ]


def _facts_from_report(report: dict[str, Any]) -> tuple[dict[str, Any], str]:
    for stage in report.get("stages", []):
        if stage.get("id") != "structured-facts":
            continue
        output = stage.get("output") or {}
        facts = output.get("current", output)
        if isinstance(facts, dict):
            return facts, str(stage.get("source") or "mock")
    return {}, "mock"


def _record_attempts(report: dict[str, Any], input_sha256: str) -> list[dict[str, Any]]:
    for stage in report.get("stages", []):
        if stage.get("id") != "structured-facts":
            continue
        attempts = (stage.get("output") or {}).get("attempts") or []
        selected = list((report.get("guardrail_selection") or {}).get("selected") or [])
        records = []
        for item in attempts:
            status = item.get("status", "fail")
            if status not in {"pass", "warn", "fail", "unavailable"}:
                status = "fail"
            records.append(
                {
                    "number": int(item.get("attempt", len(records) + 1)),
                    "input_sha256": input_sha256,
                    "selected_mechanisms": selected,
                    "status": status,
                }
            )
        if records:
            return records
    return [
        {
            "number": 1,
            "input_sha256": input_sha256,
            "selected_mechanisms": list(
                (report.get("guardrail_selection") or {}).get("selected") or []
            ),
            "status": "fail",
        }
    ]


def reasoning_record_from_report(report: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic v1 reasoning record from a runner report."""

    input_shape = {
        "example": report.get("example"),
        "scenario": report.get("scenario"),
        "mode": report.get("mode"),
        "requested_stage": report.get("requested_stage"),
        "requested_guardrails": report.get("requested_guardrails"),
        "max_repair_attempts": report.get("max_repair_attempts"),
    }
    input_sha256 = _canonical_sha256(input_shape)
    facts, facts_source = _facts_from_report(report)
    confidence = facts.get("confidence", 1.0)
    if not isinstance(confidence, (int, float)):
        confidence = 1.0

    fact_records = [
        {
            "id": _identifier("fact", key),
            "type": key,
            "value": value,
            "source": _record_source(facts_source),
            "confidence": float(confidence),
        }
        for key, value in sorted(facts.items())
        if key != "confidence"
    ]

    mechanisms: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for stage in _mechanism_stages(report):
        output = stage["output"]
        mechanism_id = output["mechanism"]
        source = _record_source(str(stage.get("source") or "mock"))
        attempts = output.get("attempts") or [
            {"attempt": 1, "findings": output.get("findings") or []}
        ]
        mechanism_findings = [
            finding
            for attempt in attempts
            for finding in attempt.get("findings") or []
            if isinstance(finding, dict)
        ]
        mechanisms.append(
            {
                "id": mechanism_id,
                "tier": stage.get("tier", "community"),
                "availability": _availability(source),
                "source": source,
                "runtime_executed": any(
                    _runtime_executed(finding) for finding in mechanism_findings
                ),
            }
        )
        for attempt in attempts:
            number = int(attempt.get("attempt", 1))
            for item in attempt.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                rule_id = str(item.get("rule_id") or "unclassified")
                finding_id = _identifier(
                    "finding", f"{mechanism_id}-{number}-{rule_id}"
                )
                evidence_id = _identifier("evidence", finding_id)
                evidence_value = item.get("evidence")
                if evidence_value is None:
                    evidence_value = {"status": item.get("status", "fail")}
                evidence.append(
                    {
                        "id": evidence_id,
                        "source_kind": "local_runtime"
                        if _runtime_executed(item)
                        else "fixture",
                        "reference": rule_id,
                        "observed": evidence_value,
                        "synthetic": True,
                    }
                )
                status = item.get("status", "fail")
                if status not in {"pass", "warn", "fail", "unavailable"}:
                    status = "fail"
                findings.append(
                    {
                        "id": finding_id,
                        "attempt": number,
                        "mechanism_id": mechanism_id,
                        "tier": stage.get("tier", "community"),
                        "status": status,
                        "rule_id": rule_id,
                        "severity": item.get("severity", "error"),
                        "message": str(item.get("message") or rule_id),
                        "repair_hint": str(item.get("repair_hint") or ""),
                        "evidence_refs": [evidence_id],
                    }
                )

    final_status = report.get("final_status", "fail")
    disposition = {
        "pass": "complete",
        "warn": "review_required",
    }.get(final_status, "unresolved")
    return {
        "schema_version": REASONING_RECORD_VERSION,
        "record_id": f"rr-{input_sha256[:24]}",
        "input_sha256": input_sha256,
        "scenario": {
            "id": str(report.get("scenario") or "unknown"),
            "label": str(report.get("scenario") or "unknown"),
            "synthetic": True,
        },
        "provenance": {
            "mode": "live" if report.get("resolved_mode") == "live" else "fixture",
            "sdk_python_version": SDK_VERSION,
            "sdk_native_version": SDK_VERSION,
            "community_complete": True,
        },
        "mechanisms": mechanisms,
        "facts": fact_records,
        "findings": findings,
        "evidence": evidence,
        "attempts": _record_attempts(report, input_sha256),
        "final": {
            "review_disposition": disposition,
            "summary": str(report.get("summary") or "No summary available."),
            "finding_refs": [item["id"] for item in findings],
            "evidence_refs": [item["id"] for item in evidence],
        },
    }
