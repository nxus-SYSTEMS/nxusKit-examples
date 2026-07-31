"""Pure Polars tables and direct Altair charts for reasoning records."""

from __future__ import annotations

from typing import Any, Iterable

import altair as alt
import polars as pl

from claims_audit import PROFILE_ROWS


TABLE_SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "stages": {
        "stage": pl.String,
        "attempt": pl.Int64,
        "status": pl.String,
    },
    "findings": {
        "id": pl.String,
        "attempt": pl.Int64,
        "mechanism_id": pl.String,
        "tier": pl.String,
        "status": pl.String,
        "rule_id": pl.String,
        "severity": pl.String,
        "message": pl.String,
        "repair_hint": pl.String,
        "evidence_refs": pl.List(pl.String),
    },
    "attempts": {
        "number": pl.Int64,
        "input_sha256": pl.String,
        "selected_mechanisms": pl.List(pl.String),
        "status": pl.String,
    },
    "mechanisms": {
        "id": pl.String,
        "tier": pl.String,
        "availability": pl.String,
        "source": pl.String,
        "runtime_executed": pl.Boolean,
    },
    "facts": {
        "id": pl.String,
        "type": pl.String,
        "value": pl.Object,
        "source": pl.String,
        "confidence": pl.Float64,
    },
    "evidence": {
        "id": pl.String,
        "source_kind": pl.String,
        "reference": pl.String,
        "observed": pl.Object,
        "synthetic": pl.Boolean,
    },
    "claims_exception_categories": {
        "rule_id": pl.String,
        "severity": pl.String,
        "count": pl.Int64,
    },
    "claims_scale_profiles": {
        "profile": pl.String,
        "row_count": pl.Int64,
    },
}


def _table(
    rows: Iterable[dict[str, Any]], schema: dict[str, pl.DataType]
) -> pl.DataFrame:
    values = list(rows)
    if not values:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(values, schema=schema, strict=False)


def record_tables(record: dict[str, Any]) -> dict[str, pl.DataFrame]:
    """Project canonical record sections into labeled tables without rerunning it."""

    tables = {
        name: _table(record.get(name, []), schema)
        for name, schema in TABLE_SCHEMAS.items()
        if name
        not in {"stages", "claims_exception_categories", "claims_scale_profiles"}
    }
    tables["stages"] = _table(_stage_rows(record), TABLE_SCHEMAS["stages"])
    tables["claims_exception_categories"] = _table(
        _claims_exception_categories(record),
        TABLE_SCHEMAS["claims_exception_categories"],
    )
    tables["claims_scale_profiles"] = _table(
        _claims_scale_profiles(record), TABLE_SCHEMAS["claims_scale_profiles"]
    )
    return tables


def _inline_chart(values: list[dict[str, Any]]) -> alt.Chart:
    return alt.Chart(alt.InlineData(values=values))


def _count_rows(rows: Iterable[dict[str, Any]], *fields: str) -> list[dict[str, Any]]:
    counts: dict[tuple[str, ...], int] = {}
    for row in rows:
        key = tuple(str(row.get(field, "unknown")) for field in fields)
        counts[key] = counts.get(key, 0) + 1
    return [
        {**dict(zip(fields, key, strict=True)), "count": count}
        for key, count in sorted(counts.items())
    ]


def _stage_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Label the record's real attempts and final review without inferring outcomes."""

    attempts = record.get("attempts", [])
    rows = [
        {
            "stage": "baseline" if index == 0 else "repair",
            "attempt": int(attempt.get("number", index + 1)),
            "status": str(attempt.get("status", "unknown")),
        }
        for index, attempt in enumerate(attempts)
        if isinstance(attempt, dict)
    ]
    final = record.get("final")
    if isinstance(final, dict):
        rows.append(
            {
                "stage": "final review",
                "attempt": rows[-1]["attempt"] if rows else 0,
                "status": str(final.get("review_disposition", "unknown")),
            }
        )
    return rows


def _claims_exception_categories(record: dict[str, Any]) -> list[dict[str, Any]]:
    scenario = record.get("scenario")
    if not isinstance(scenario, dict) or scenario.get("id") != "synthetic-claims-audit":
        return []
    findings = [
        finding for finding in record.get("findings", []) if isinstance(finding, dict)
    ]
    return _count_rows(findings, "rule_id", "severity")


def _claims_scale_profiles(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose only the existing bounded expansion profiles for claims records."""

    scenario = record.get("scenario")
    if not isinstance(scenario, dict) or scenario.get("id") != "synthetic-claims-audit":
        return []
    return [
        {"profile": profile, "row_count": row_count}
        for profile, row_count in PROFILE_ROWS.items()
    ]


def _latest_bn_values(record: dict[str, Any]) -> list[dict[str, float]]:
    latest: dict[str, Any] | None = None
    for evidence in record.get("evidence", []):
        observed = evidence.get("observed") if isinstance(evidence, dict) else None
        if (
            isinstance(observed, dict)
            and {
                "probability",
                "threshold",
            }
            <= observed.keys()
        ):
            latest = observed
    if latest is None:
        return []
    probability = latest.get("probability")
    threshold = latest.get("threshold")
    if not isinstance(probability, (int, float)) or not isinstance(
        threshold, (int, float)
    ):
        return []
    return [
        {"metric": "observed_probability", "value": float(probability)},
        {"metric": "review_threshold", "value": float(threshold)},
    ]


def chart_specs(record: dict[str, Any]) -> dict[str, alt.Chart]:
    """Render only truthful, non-secret visual summaries from a record."""

    findings = list(record.get("findings", []))
    mechanisms = list(record.get("mechanisms", []))
    stages = _stage_rows(record)
    charts: dict[str, alt.Chart] = {
        "stage_progression": _inline_chart(stages)
        .mark_line(point=True)
        .encode(
            x=alt.X("stage:N", title="Record stage"),
            y=alt.Y("attempt:Q", title="Attempt"),
            color=alt.Color("status:N", title="Status"),
            tooltip=["stage:N", "attempt:Q", "status:N"],
        ),
        "findings_by_status": _inline_chart(_count_rows(findings, "status"))
        .mark_bar()
        .encode(
            x=alt.X("status:N", title="Finding status"),
            y=alt.Y("count:Q", title="Findings"),
            color=alt.Color("status:N", legend=None),
        ),
        "findings_by_category": _inline_chart(
            _count_rows(findings, "mechanism_id", "status", "severity")
        )
        .mark_bar()
        .encode(
            x=alt.X("mechanism_id:N", title="Mechanism"),
            y=alt.Y("count:Q", title="Findings"),
            color=alt.Color("status:N", title="Status"),
            column=alt.Column("severity:N", title="Severity"),
        ),
        "attempt_findings": _inline_chart(_count_rows(findings, "attempt", "status"))
        .mark_bar()
        .encode(
            x=alt.X("attempt:N", title="Attempt"),
            y=alt.Y("count:Q", title="Findings"),
            color=alt.Color("status:N", title="Status"),
        ),
        "mechanism_availability": _inline_chart(
            [
                {
                    "mechanism": str(item.get("id", "unknown")),
                    "availability": str(item.get("availability", "unknown")),
                    "runtime_executed": bool(item.get("runtime_executed", False)),
                }
                for item in mechanisms
            ]
        )
        .mark_rect()
        .encode(
            x=alt.X("mechanism:N", title="Mechanism"),
            y=alt.Y("availability:N", title="Availability"),
            color=alt.Color("runtime_executed:N", title="Executed"),
        ),
    }
    bn_values = _latest_bn_values(record)
    if bn_values:
        charts["bn_threshold"] = (
            _inline_chart(bn_values)
            .mark_bar()
            .encode(
                x=alt.X("metric:N", title="Bayesian metric"),
                y=alt.Y("value:Q", title="Probability"),
                color=alt.Color("metric:N", legend=None),
            )
        )
    return charts
