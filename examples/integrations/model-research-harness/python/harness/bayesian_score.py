"""Bayesian confidence aggregation for sparse model research signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def posterior_confidence(
    results: list[dict[str, Any]],
    config: dict[str, Any] | None,
    *,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if cfg.get("engine") == "nxuskit-bn":
        return nxuskit_bn_confidence(results, cfg, config_dir)
    return beta_confidence(results, cfg)


def beta_confidence(
    results: list[dict[str, Any]], cfg: dict[str, Any]
) -> dict[str, Any]:
    alpha = float(cfg.get("prior_alpha", 2.0))
    beta = float(cfg.get("prior_beta", 2.0))
    evidence: list[dict[str, Any]] = []

    for result in results:
        score = float(result.get("score", {}).get("score", 0.0))
        weight = float(result.get("bayesian_weight", 1.0))
        alpha += score * weight
        beta += (1.0 - score) * weight
        evidence.append(
            {
                "test": result.get("test_id"),
                "provider": result.get("provider_id"),
                "score": round(score, 4),
                "weight": weight,
            }
        )

    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1.0))
    return {
        "engine": "bayesian",
        "posterior_alpha": round(alpha, 4),
        "posterior_beta": round(beta, 4),
        "mean_confidence": round(mean, 4),
        "uncertainty": round(variance**0.5, 4),
        "evidence": evidence,
    }


def nxuskit_bn_confidence(
    results: list[dict[str, Any]],
    cfg: dict[str, Any],
    config_dir: Path | None,
) -> dict[str, Any]:
    try:
        from nxuskit.bn import BnEvidence, BnNetwork
    except Exception as exc:  # noqa: BLE001
        return handle_bn_unavailable(results, cfg, f"{type(exc).__name__}: {exc}")

    model_path = resolve_path(cfg.get("model_file"), config_dir)
    if model_path is None:
        return handle_bn_unavailable(results, cfg, "nxuskit-bn requires model_file")

    query_variable = cfg.get("query_variable", "model_fit")
    query_state = cfg.get("query_state", "good")
    algorithm = cfg.get("algorithm", "ve")
    evidence_data = dict(cfg.get("evidence") or {})
    evidence_data.update(
        evidence_from_results(results, cfg.get("evidence_from_results") or [])
    )

    try:
        with BnNetwork.load(str(model_path)) as net, BnEvidence() as ev:
            for variable, state in evidence_data.items():
                ev.set_discrete(net, str(variable), str(state))
            with net.infer(ev, str(algorithm)) as inference:
                marginal = inference.marginal(str(query_variable))
        confidence = float(marginal.get(str(query_state), 0.0))
        return {
            "engine": "nxuskit-bn",
            "mean_confidence": round(confidence, 4),
            "uncertainty": round(confidence * (1.0 - confidence), 4),
            "query_variable": query_variable,
            "query_state": query_state,
            "algorithm": algorithm,
            "marginal": marginal,
            "evidence": [
                {"variable": key, "state": value}
                for key, value in sorted(evidence_data.items())
            ],
            "model_file": str(model_path),
        }
    except Exception as exc:  # noqa: BLE001
        return handle_bn_unavailable(results, cfg, f"{type(exc).__name__}: {exc}")


def evidence_from_results(
    results: list[dict[str, Any]], specs: list[dict[str, Any]]
) -> dict[str, str]:
    by_test = {result["test_id"]: result for result in results}
    evidence: dict[str, str] = {}
    for spec in specs:
        variable = spec.get("variable")
        if not variable:
            continue
        test_id = spec.get("test_id")
        result = by_test.get(test_id) if test_id else None
        score = float((result or {}).get("score", {}).get("score", 0.0))
        threshold = float(spec.get("threshold", 0.5))
        evidence[str(variable)] = str(
            spec.get("pass_state", "yes")
            if score >= threshold
            else spec.get("fail_state", "no")
        )
    return evidence


def handle_bn_unavailable(
    results: list[dict[str, Any]], cfg: dict[str, Any], reason: str
) -> dict[str, Any]:
    behavior = cfg.get("on_engine_unavailable", "fallback-beta")
    if behavior == "fallback-beta":
        fallback = beta_confidence(results, cfg)
        fallback["engine"] = "beta-fallback"
        fallback["engine_unavailable"] = reason
        return fallback
    return {
        "engine": "nxuskit-bn",
        "mean_confidence": 0.0,
        "uncertainty": 1.0,
        "engine_unavailable": reason,
        "evidence": [],
    }


def resolve_path(value: Any, config_dir: Path | None) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    base = config_dir or Path.cwd()
    return (base / path).resolve()
