"""Core runner for the model research harness example."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .bayesian_score import posterior_confidence
from .clips_policy import evaluate_policy
from .external_command import run_external_test
from .lifecycle import recommend
from .providers import call_provider, capability_truth
from .scorers import evaluate_assertions, parse_jsonish, score_assertions


def run_config(
    config: dict[str, Any],
    *,
    mode: str,
    provider_override: str | None = None,
    model_override: str | None = None,
    output_dir: Path | None = None,
    allow_external_commands: bool = False,
    allow_lifecycle_mutations: bool = False,
) -> tuple[
    list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]
]:
    providers = {provider["id"]: provider for provider in config["providers"]}
    results: list[dict[str, Any]] = []
    truth: list[dict[str, Any]] = []

    for test in config["tests"]:
        provider_ids = test.get("provider_ids") or list(providers)
        adapter = str(test.get("adapter", "")).replace("-", "_")
        if adapter == "external_command":
            provider_id = provider_ids[0]
            provider = providers[provider_id]
            item = run_external_test(
                test,
                config,
                provider,
                output_dir=output_dir,
                allow_external_commands=allow_external_commands,
                allow_lifecycle_mutations=allow_lifecycle_mutations,
            )
            item["policy"] = evaluate_policy(
                item,
                config.get("policy"),
                config_dir=Path(str(config.get("_config_dir", "."))),
            )
            if item["policy"]["status"] == "fail":
                item["status"] = "fail"
            results.append(item)
            truth.append(
                capability_truth(
                    provider, {"harness_validated": True, "harness_repaired": False}
                )
            )
            continue

        for provider_id in provider_ids:
            provider = providers[provider_id]
            response = call_provider(
                provider, test, mode, provider_override, model_override
            )
            effective_provider_id = str(response.get("provider_id") or provider_id)
            parsed, parse_error = parse_jsonish(response["content"])
            assertions = evaluate_assertions(
                response["content"], test.get("assertions") or []
            )
            score = score_assertions(assertions)
            item = {
                "test_id": test["id"],
                "provider_id": effective_provider_id,
                "model": response.get("model"),
                "source": response.get("source"),
                "status": "pass" if score["failed"] == 0 else "fail",
                "output": response["content"],
                "parsed_output": parsed,
                "parse_error": parse_error,
                "assertions": assertions,
                "score": score,
                "metadata": response.get("metadata") or {},
                "bayesian_weight": test.get("bayesian_weight", 1.0),
            }
            item["policy"] = evaluate_policy(
                item,
                config.get("policy"),
                config_dir=Path(str(config.get("_config_dir", "."))),
            )
            if item["policy"]["status"] == "fail":
                item["status"] = "fail"
            results.append(item)
            observed_provider = {
                **provider,
                "id": effective_provider_id,
                "provider": effective_provider_id,
                "model": response.get("model") or provider.get("model", ""),
                "capabilities": (
                    provider.get("capabilities", {})
                    if effective_provider_id == provider_id
                    else {}
                ),
            }
            truth.append(
                capability_truth(
                    observed_provider,
                    {
                        "harness_validated": True,
                        "harness_repaired": bool(test.get("repair")),
                    },
                )
            )

    bayesian = posterior_confidence(
        results,
        config.get("bayesian"),
        config_dir=Path(str(config.get("_config_dir", "."))),
    )
    recommendations = recommend(results, config.get("actions"))
    return results, bayesian, recommendations, dedupe_truth(truth)


def dedupe_truth(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = (item["provider_id"], item.get("model"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
