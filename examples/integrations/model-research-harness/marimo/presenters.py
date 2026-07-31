"""Pure Polars tables and Altair charts for canonical harness reports."""

from __future__ import annotations

from typing import Any

import altair as alt
import polars as pl


RESULT_SCHEMA = {
    "test_id": pl.String,
    "provider_id": pl.String,
    "model": pl.String,
    "source": pl.String,
    "status": pl.String,
    "score": pl.Float64,
    "passed": pl.Int64,
    "failed": pl.Int64,
}


def _frame(rows: list[dict[str, Any]], schema: dict[str, pl.DataType]) -> pl.DataFrame:
    return (
        pl.DataFrame(rows, schema=schema, strict=False)
        if rows
        else pl.DataFrame(schema=schema)
    )


def _result_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "test_id": str(item.get("test_id", "")),
            "provider_id": str(item.get("provider_id", "")),
            "model": str(item.get("model", "")),
            "source": str(item.get("source", "")),
            "status": str(item.get("status", "")),
            "score": float((item.get("score") or {}).get("score", 0.0)),
            "passed": int((item.get("score") or {}).get("passed", 0)),
            "failed": int((item.get("score") or {}).get("failed", 0)),
        }
        for item in report.get("results", [])
        if isinstance(item, dict)
    ]


def report_tables(report: dict[str, Any]) -> dict[str, pl.DataFrame]:
    """Project safe report metadata; never expose output, prompts, or credentials."""

    results = _result_rows(report)
    policy = [
        {
            "provider": str(item.get("provider", "")),
            "candidate_action": str(item.get("candidate_action", "")),
            "confidence": float(item.get("confidence", 0.0)),
            "requires_approval": bool(item.get("requires_approval", False)),
        }
        for item in report.get("policy_recommendations", [])
        if isinstance(item, dict)
    ]
    confidence = report.get("bayesian_confidence") or {}
    return {
        "results": _frame(results, RESULT_SCHEMA),
        "policy": _frame(
            policy,
            {
                "provider": pl.String,
                "candidate_action": pl.String,
                "confidence": pl.Float64,
                "requires_approval": pl.Boolean,
            },
        ),
        "confidence": _frame(
            [
                {
                    "mean_confidence": float(confidence.get("mean_confidence", 0.0)),
                    "uncertainty": float(confidence.get("uncertainty", 0.0)),
                }
            ]
            if confidence
            else [],
            {"mean_confidence": pl.Float64, "uncertainty": pl.Float64},
        ),
        "capabilities": _frame(
            [
                item
                for item in report.get("capability_truth_table", [])
                if isinstance(item, dict)
            ],
            {
                "provider_id": pl.String,
                "provider": pl.String,
                "model": pl.String,
                "native_strict_schema": pl.Boolean,
                "json_mode": pl.Boolean,
                "harness_validated": pl.Boolean,
                "harness_repaired": pl.Boolean,
                "thinking_control": pl.String,
                "tool_calling": pl.String,
            },
        ),
        "failures": _frame(
            [row for row in results if row["status"] != "pass"], RESULT_SCHEMA
        ),
    }


def _chart(values: list[dict[str, Any]]) -> alt.Chart:
    return alt.Chart(alt.InlineData(values=values))


def report_charts(report: dict[str, Any]) -> dict[str, alt.Chart]:
    """Chart only values actually measured by the canonical report."""

    results = _result_rows(report)
    rankings: dict[str, list[float]] = {}
    for row in results:
        rankings.setdefault(row["provider_id"], []).append(row["score"])
    ranking_rows = [
        {"provider_id": provider, "score": sum(scores) / len(scores)}
        for provider, scores in sorted(rankings.items())
    ]
    confidence = report.get("bayesian_confidence") or {}
    capability_rows = [
        {
            "provider_id": str(row.get("provider_id", "")),
            "json_mode": bool(row.get("json_mode", False)),
            "harness_validated": bool(row.get("harness_validated", False)),
        }
        for row in report.get("capability_truth_table", [])
        if isinstance(row, dict)
    ]
    return {
        "provider_test_heatmap": _chart(results)
        .mark_rect()
        .encode(x="test_id:N", y="provider_id:N", color="score:Q"),
        "score_ranking": _chart(ranking_rows)
        .mark_bar()
        .encode(x="provider_id:N", y="score:Q"),
        "pass_fail": _chart(results).mark_bar().encode(x="status:N", y="count():Q"),
        "confidence": _chart(
            [
                {
                    "metric": "mean_confidence",
                    "value": float(confidence.get("mean_confidence", 0.0)),
                },
                {
                    "metric": "uncertainty",
                    "value": float(confidence.get("uncertainty", 0.0)),
                },
            ]
        )
        .mark_bar()
        .encode(x="metric:N", y="value:Q"),
        "capability_truth": _chart(capability_rows)
        .mark_rect()
        .encode(x="provider_id:N", y="json_mode:N", color="harness_validated:N"),
    }
