"""Report writers for model research harness runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_report(
    config: dict[str, Any],
    results: list[dict[str, Any]],
    bayesian: dict[str, Any],
    recommendations: list[dict[str, Any]],
    truth_table: list[dict[str, Any]],
    compatibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed = sum(1 for result in results if result["status"] != "pass")
    return {
        "example": "model-research-harness",
        "config_id": config.get("id"),
        "final_status": "pass" if failed == 0 else "fail",
        "results": results,
        "bayesian_confidence": bayesian,
        "policy_recommendations": recommendations,
        "capability_truth_table": truth_table,
        "compatibility_report": compatibility or {},
    }


def write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(markdown_summary(report), encoding="utf-8")


def markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        f"# Model Research Harness: {report['config_id']}",
        "",
        f"Final status: **{report['final_status']}**",
        "",
        "## Scenario Matrix",
        "",
        "| Test | Provider | Status | Score |",
        "|------|----------|--------|-------|",
    ]
    for result in report["results"]:
        lines.append(
            f"| {result['test_id']} | {result['provider_id']} | {result['status']} | {result['score']['score']:.2f} |"
        )
    external_results = [
        result
        for result in report["results"]
        if result.get("metadata", {}).get("adapter") == "external-command"
    ]
    if external_results:
        lines.extend(
            [
                "",
                "## External Adapter Artifacts",
                "",
                "| Test | Executed | Output JSON | Summary |",
                "|------|----------|-------------|---------|",
            ]
        )
        for result in external_results:
            metadata = result.get("metadata", {})
            lines.append(
                "| {test} | {executed} | {output_json} | {summary_md} |".format(
                    test=result["test_id"],
                    executed=metadata.get("executed", False),
                    output_json=metadata.get("output_json", ""),
                    summary_md=metadata.get("summary_md", ""),
                )
            )
    lines.extend(
        [
            "",
            "## Provider/Model Ranking",
            "",
            "| Provider | Action | Confidence | Reason |",
            "|----------|--------|------------|--------|",
        ]
    )
    for item in report["policy_recommendations"]:
        lines.append(
            f"| {item['provider']} | {item['candidate_action']} | {item['confidence']:.2f} | {item['reason']} |"
        )
    lines.extend(
        [
            "",
            "## Capability Truth Table",
            "",
            "| Provider | Native Strict Schema | JSON Mode | Harness Validated | Harness Repaired | Tool Calling | Thinking Control |",
            "|----------|----------------------|-----------|-------------------|------------------|--------------|------------------|",
        ]
    )
    for item in report["capability_truth_table"]:
        lines.append(
            "| {provider_id} | {native_strict_schema} | {json_mode} | {harness_validated} | {harness_repaired} | {tool_calling} | {thinking_control} |".format(
                **item
            )
        )
    lines.append("")
    return "\n".join(lines)
