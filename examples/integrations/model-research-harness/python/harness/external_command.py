"""Explicit external-command adapter for migration parity runs.

The public harness fails closed: configs can describe external commands, but
they only execute when the CLI caller passes --allow-external. Commands are run
without a shell and should point at a known runner owned by the caller.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import csv


PLACEHOLDER = re.compile(r"\{([^{}]+)\}")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
STATUS_SCORES = {
    "PASS": 1.0,
    "WARN": 0.75,
    "PARTIAL": 0.5,
    "POOR": 0.25,
    "EMPTY": 0.0,
    "FAIL": 0.0,
    "ERROR": 0.0,
}


class ExternalCommandError(RuntimeError):
    """Raised when an external adapter config cannot be executed."""


def run_external_test(
    test: dict[str, Any],
    config: dict[str, Any],
    provider: dict[str, Any],
    *,
    output_dir: Path | None,
    allow_external_commands: bool,
    allow_lifecycle_mutations: bool,
) -> dict[str, Any]:
    spec = test.get("external_command") or {}
    adapter_output_dir = (
        (output_dir or Path(".tmp/model-research-harness"))
        / "adapters"
        / str(test["id"])
    )
    if not adapter_output_dir.is_absolute():
        adapter_output_dir = (Path.cwd() / adapter_output_dir).resolve()
    provider_id = provider["id"]
    model = spec.get("label") or provider.get("model") or "external-command"

    if not allow_external_commands:
        return build_external_item(
            test,
            provider_id,
            model,
            "fail",
            0.0,
            "external commands require --allow-external",
            {
                "adapter": "external-command",
                "executed": False,
                "requires_flag": "--allow-external",
                "adapter_output_dir": str(adapter_output_dir),
            },
        )
    if spec.get("mutation") and not allow_lifecycle_mutations:
        return build_external_item(
            test,
            provider_id,
            model,
            "fail",
            0.0,
            "lifecycle mutation commands require --allow-lifecycle-mutations",
            {
                "adapter": "external-command",
                "executed": False,
                "mutation": True,
                "requires_flag": "--allow-lifecycle-mutations",
                "adapter_output_dir": str(adapter_output_dir),
            },
        )

    started = time.perf_counter()
    try:
        context = build_context(config, test, adapter_output_dir)
        argv = expand_value(spec.get("argv") or [], context)
        if not isinstance(argv, list) or not argv:
            raise ExternalCommandError(
                "external_command.argv must be a non-empty array"
            )
        argv = [str(item) for item in argv]
        cwd_text = expand_value(spec.get("cwd", context["root"]), context)
        cwd = Path(str(cwd_text)).expanduser()
        env = os.environ.copy()
        for key, value in (spec.get("env") or {}).items():
            env[str(key)] = str(expand_value(value, context))
        adapter_output_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=float(spec.get("timeout_seconds", 600)),
            check=False,
        )
        duration = time.perf_counter() - started
        output_json = load_optional_json(spec.get("output_json"), context)
        output_csv = load_optional_csv(spec.get("output_csv"), context)
        status, score, detail, parsed = normalize_external_report(
            {"json": output_json, "csv": output_csv},
            proc.returncode,
            spec,
        )
        metadata = {
            "adapter": "external-command",
            "executed": True,
            "argv": argv,
            "cwd": str(cwd),
            "exit_code": proc.returncode,
            "duration_seconds": round(duration, 3),
            "stdout_tail": tail(proc.stdout),
            "stderr_tail": tail(proc.stderr),
            "adapter_output_dir": str(adapter_output_dir),
            "output_json": str(
                resolve_optional_path(spec.get("output_json"), context) or ""
            ),
            "output_csv": str(
                resolve_optional_path(spec.get("output_csv"), context) or ""
            ),
            "summary_md": str(
                resolve_optional_path(spec.get("summary_md"), context) or ""
            ),
        }
        return build_external_item(
            test, provider_id, model, status, score, detail, metadata, parsed
        )
    except Exception as exc:  # noqa: BLE001 - adapter failures must be reported as harness results
        duration = time.perf_counter() - started
        return build_external_item(
            test,
            provider_id,
            model,
            "fail",
            0.0,
            str(exc),
            {
                "adapter": "external-command",
                "executed": allow_external_commands,
                "duration_seconds": round(duration, 3),
                "adapter_output_dir": str(adapter_output_dir),
            },
        )


def build_external_item(
    test: dict[str, Any],
    provider_id: str,
    model: str,
    status: str,
    score: float,
    detail: str,
    metadata: dict[str, Any],
    parsed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    passed = status == "pass"
    return {
        "test_id": test["id"],
        "provider_id": provider_id,
        "model": model,
        "source": "external",
        "status": status,
        "output": detail,
        "parsed_output": parsed or {"detail": detail},
        "parse_error": None,
        "assertions": [
            {
                "type": "external-command",
                "status": "pass" if passed else "fail",
                "detail": detail,
                "weight": 1.0,
            }
        ],
        "score": {
            "score": round(score, 4),
            "passed": 1 if passed else 0,
            "failed": 0 if passed else 1,
            "unsupported": 0,
        },
        "metadata": metadata,
        "bayesian_weight": test.get("bayesian_weight", 1.0),
    }


def build_context(
    config: dict[str, Any], test: dict[str, Any], adapter_output_dir: Path
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    config_dir = Path(str(config.get("_config_dir", root / "configs")))
    merged_vars: dict[str, Any] = {}
    merged_vars.update(config.get("vars") or {})
    merged_vars.update(test.get("vars") or {})
    return {
        "root": str(root),
        "config_dir": str(config_dir),
        "adapter_output_dir": str(adapter_output_dir),
        "python": sys.executable,
        "vars": merged_vars,
    }


def expand_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [expand_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: expand_value(item, context) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in {"root", "config_dir", "adapter_output_dir", "python"}:
            return str(context[key])
        if key.startswith("env:"):
            env_name = key.split(":", 1)[1]
            if env_name not in os.environ:
                raise ExternalCommandError(
                    f"required environment variable {env_name} is not set"
                )
            return os.environ[env_name]
        if key.startswith("var:"):
            var_name = key.split(":", 1)[1]
            if var_name not in context["vars"]:
                raise ExternalCommandError(
                    f"required config variable {var_name} is not set"
                )
            return str(context["vars"][var_name])
        raise ExternalCommandError(f"unknown external-command placeholder {{{key}}}")

    return PLACEHOLDER.sub(replace, value)


def resolve_optional_path(value: Any, context: dict[str, Any]) -> Path | None:
    if not value:
        return None
    expanded = Path(str(expand_value(value, context))).expanduser()
    if expanded.is_absolute():
        return expanded
    return Path(context["adapter_output_dir"]) / expanded


def load_optional_json(value: Any, context: dict[str, Any]) -> Any:
    path = resolve_optional_path(value, context)
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional_csv(
    value: Any, context: dict[str, Any]
) -> list[dict[str, str]] | None:
    path = resolve_optional_path(value, context)
    if path is None or not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_external_report(
    data: Any, exit_code: int, spec: dict[str, Any]
) -> tuple[str, float, str, dict[str, Any]]:
    strategy = spec.get("result_strategy", "exit-code")
    thresholds = spec.get("thresholds") or {}
    if strategy == "devops-capabilities":
        return normalize_capabilities(unwrap_csv(data), thresholds, exit_code)
    if strategy == "devops-common-sense":
        return normalize_common_sense(unwrap_json(data), thresholds)
    if strategy == "devops-tool-intent":
        return normalize_tool_intent(unwrap_json(data), thresholds)
    if strategy == "devops-safe-labs":
        return normalize_safe_labs(unwrap_json(data), thresholds)
    if strategy == "devops-pipeline":
        return normalize_pipeline(unwrap_json(data), thresholds)
    if strategy == "devops-vision":
        return normalize_vision(unwrap_json(data), thresholds)
    if strategy != "exit-code":
        return (
            "fail",
            0.0,
            f"unknown external result_strategy: {strategy}",
            {"strategy": strategy},
        )
    score = 1.0 if exit_code == 0 else 0.0
    status = "pass" if exit_code == 0 else "fail"
    return (
        status,
        score,
        f"external command exited {exit_code}",
        {"exit_code": exit_code, "strategy": strategy},
    )


def unwrap_json(data: Any) -> Any:
    if isinstance(data, dict) and "json" in data and "csv" in data:
        return data.get("json")
    return data


def unwrap_csv(data: Any) -> list[dict[str, str]] | None:
    if isinstance(data, dict) and "json" in data and "csv" in data:
        csv_data = data.get("csv")
        return csv_data if isinstance(csv_data, list) else None
    return data if isinstance(data, list) else None


def normalize_capabilities(
    rows: list[dict[str, str]] | None,
    thresholds: dict[str, Any],
    exit_code: int,
) -> tuple[str, float, str, dict[str, Any]]:
    if exit_code != 0:
        return (
            "fail",
            0.0,
            f"capability runner exited {exit_code}",
            {"strategy": "devops-capabilities", "exit_code": exit_code},
        )
    rows = rows or []
    if not rows:
        return (
            "fail",
            0.0,
            "capability runner produced no CSV rows",
            {"strategy": "devops-capabilities", "row_count": 0},
        )

    min_json_output = int(thresholds.get("min_json_output_level", 0))
    min_json_input = int(thresholds.get("min_json_input_level", 0))
    min_image_to_json = int(thresholds.get("min_image_to_json_level", 0))
    require_tools = bool(thresholds.get("require_tools", False))
    per_row = []
    for row in rows:
        json_output = intish(row.get("JSONOutput"))
        json_input = intish(row.get("JSONInput"))
        image_to_json = intish(row.get("ImageToJSON"))
        tools_ok = symbol_passes(row.get("Tools", "")) if require_tools else True
        checks = {
            "json_output": json_output >= min_json_output,
            "json_input": json_input >= min_json_input,
            "image_to_json": image_to_json >= min_image_to_json,
            "tools": tools_ok,
        }
        scored_levels = [json_output / 3.0]
        if min_json_input:
            scored_levels.append(json_input / 3.0)
        if min_image_to_json:
            scored_levels.append(image_to_json / 3.0)
        if require_tools:
            scored_levels.append(1.0 if tools_ok else 0.0)
        per_row.append(
            {
                "model": row.get("Model", ""),
                "json_output_level": json_output,
                "json_input_level": json_input,
                "image_to_json_level": image_to_json,
                "tools_ok": tools_ok,
                "checks": checks,
                "score": sum(scored_levels) / len(scored_levels),
            }
        )

    score = sum(float(row["score"]) for row in per_row) / len(per_row)
    passed = all(all(row["checks"].values()) for row in per_row)
    detail = f"{sum(1 for row in per_row if all(row['checks'].values()))}/{len(per_row)} capability rows met thresholds"
    return (
        "pass" if passed else "fail",
        score,
        detail,
        {
            "strategy": "devops-capabilities",
            "row_count": len(per_row),
            "thresholds": {
                "min_json_output_level": min_json_output,
                "min_json_input_level": min_json_input,
                "min_image_to_json_level": min_image_to_json,
                "require_tools": require_tools,
            },
            "rows": per_row,
        },
    )


def normalize_common_sense(
    data: Any, thresholds: dict[str, Any]
) -> tuple[str, float, str, dict[str, Any]]:
    results = data.get("results", []) if isinstance(data, dict) else []
    total = len(results)
    target_count = sum(1 for row in results if row.get("target_candidate"))
    error_count = sum(
        1
        for row in results
        if any(
            (row.get(kind) or {}).get("error")
            for kind in ("simple", "constrained", "enhanced")
        )
    )
    min_targets = int(thresholds.get("min_target_candidates", 1))
    score = target_count / total if total else 0.0
    passed = total > 0 and target_count >= min_targets and error_count == 0
    detail = f"{target_count}/{total} target candidates; {error_count} model errors"
    return (
        "pass" if passed else "fail",
        score,
        detail,
        {
            "strategy": "devops-common-sense",
            "target_candidates": target_count,
            "total": total,
            "errors": error_count,
        },
    )


def normalize_tool_intent(
    data: Any, thresholds: dict[str, Any]
) -> tuple[str, float, str, dict[str, Any]]:
    results = data.get("results", []) if isinstance(data, dict) else []
    total = len(results)
    pass_count = sum(1 for row in results if row.get("pass_smoke"))
    min_pass = int(thresholds.get("min_pass_count", total))
    score = pass_count / total if total else 0.0
    detail = f"{pass_count}/{total} tool-intent rows passed"
    return (
        "pass" if total > 0 and pass_count >= min_pass else "fail",
        score,
        detail,
        {
            "strategy": "devops-tool-intent",
            "passed": pass_count,
            "total": total,
        },
    )


def normalize_safe_labs(
    data: Any, thresholds: dict[str, Any]
) -> tuple[str, float, str, dict[str, Any]]:
    results = data.get("results", []) if isinstance(data, dict) else []
    rows = [item.get("row", {}) for item in results if isinstance(item, dict)]
    pass_statuses = set(thresholds.get("pass_statuses", ["PASS"]))
    min_value_accuracy = float(thresholds.get("min_value_accuracy", 1.0))
    scores = []
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "ERROR")).upper()
        status_counts[status] = status_counts.get(status, 0) + 1
        if row.get("value_accuracy") is not None:
            scores.append(float(row.get("value_accuracy") or 0.0))
        else:
            scores.append(STATUS_SCORES.get(status, 0.0))
    score = sum(scores) / len(scores) if scores else 0.0
    passed = (
        bool(rows)
        and all(str(row.get("status", "")).upper() in pass_statuses for row in rows)
        and score >= min_value_accuracy
    )
    detail = f"{len(rows)} safe-labs rows; score={score:.2f}; statuses={status_counts}"
    return (
        "pass" if passed else "fail",
        score,
        detail,
        {
            "strategy": "devops-safe-labs",
            "status_counts": status_counts,
            "row_count": len(rows),
            "mean_score": round(score, 4),
        },
    )


def normalize_pipeline(
    data: Any, thresholds: dict[str, Any]
) -> tuple[str, float, str, dict[str, Any]]:
    result = data.get("result", data) if isinstance(data, dict) else {}
    raw_score = float(result.get("score", 0.0) or 0.0)
    min_score = float(thresholds.get("min_score", 100.0))
    score = max(0.0, min(raw_score / 100.0, 1.0))
    detail = f"pipeline score={raw_score:.1f}; found={len(result.get('found') or [])}; missing={len(result.get('missing') or [])}"
    return (
        "pass" if raw_score >= min_score else "fail",
        score,
        detail,
        {
            "strategy": "devops-pipeline",
            "score": raw_score,
            "found": result.get("found") or [],
            "missing": result.get("missing") or [],
            "extra_rows": result.get("extra_rows", 0),
        },
    )


def normalize_vision(
    data: Any, thresholds: dict[str, Any]
) -> tuple[str, float, str, dict[str, Any]]:
    entries = data if isinstance(data, list) else []
    pass_statuses = set(thresholds.get("pass_statuses", ["PASS"]))
    scores = []
    statuses: dict[str, int] = {}
    for entry in entries:
        for format_results in (entry.get("results") or {}).values():
            for result in format_results.values():
                status = str(result.get("status", "ERROR")).upper()
                statuses[status] = statuses.get(status, 0) + 1
                scores.append(
                    float(result.get("score", STATUS_SCORES.get(status, 0.0) * 100.0))
                    / 100.0
                )
    score = sum(scores) / len(scores) if scores else 0.0
    passed = bool(scores) and all(status in pass_statuses for status in statuses)
    detail = f"{len(scores)} structured extraction runs; score={score:.2f}; statuses={statuses}"
    return (
        "pass" if passed else "fail",
        score,
        detail,
        {
            "strategy": "devops-vision",
            "status_counts": statuses,
            "run_count": len(scores),
            "mean_score": round(score, 4),
        },
    )


def tail(text: str, limit: int = 4000) -> str:
    text = ANSI_ESCAPE.sub("", text)
    if len(text) <= limit:
        return text
    return text[-limit:]


def intish(value: Any) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def symbol_passes(value: Any) -> bool:
    text = str(value or "")
    return "✅" in text or text.upper() == "PASS"
