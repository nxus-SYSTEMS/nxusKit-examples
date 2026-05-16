"""Dry-run lifecycle and cache-disposition recommendations."""

from __future__ import annotations

from typing import Any


def recommend(
    results: list[dict[str, Any]], actions: dict[str, Any] | None
) -> list[dict[str, Any]]:
    cfg = actions or {}
    mode = cfg.get("mode", "dry-run")
    recommendations = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(result["provider_id"], []).append(result)

    for provider_id, provider_results in grouped.items():
        avg = sum(
            float(r.get("score", {}).get("score", 0.0)) for r in provider_results
        ) / len(provider_results)
        if avg >= 0.85:
            action = "pin"
            reason = "high confidence across the configured test set"
        elif avg >= 0.65:
            action = "keep"
            reason = "adequate score with more evidence recommended"
        else:
            action = "retest"
            reason = "low score or sparse evidence"
        recommendations.append(
            {
                "provider": provider_id,
                "candidate_action": action,
                "requires_approval": mode != "auto",
                "reason": reason,
                "confidence": round(avg, 4),
                "resource_impact": "not measured in public dry-run adapter",
                "policy_evidence": "dry-run lifecycle policy",
            }
        )
    return recommendations
