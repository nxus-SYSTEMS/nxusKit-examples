"""Composable scoring signals for harness test results."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any


def parse_jsonish(text: str) -> tuple[Any | None, str | None]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def json_path(data: Any, path: str) -> Any:
    if path == "$":
        return data
    if not path.startswith("$."):
        return None
    cur = data
    for part in path[2:].split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)]
        else:
            return None
    return cur


def evaluate_assertions(
    output_text: str, assertions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    parsed, parse_error = parse_jsonish(output_text)
    results: list[dict[str, Any]] = []
    for assertion in assertions:
        atype = assertion.get("type")
        status = "pass"
        detail = ""

        if atype == "contains":
            status = (
                "pass" if str(assertion.get("value", "")) in output_text else "fail"
            )
        elif atype == "not-contains":
            status = (
                "pass" if str(assertion.get("value", "")) not in output_text else "fail"
            )
        elif atype == "icontains":
            needle = str(assertion.get("value", "")).lower()
            status = "pass" if needle in output_text.lower() else "fail"
        elif atype == "equals":
            actual = (
                json_path(parsed, assertion.get("path", "$"))
                if parsed is not None
                else output_text
            )
            status = "pass" if actual == assertion.get("value") else "fail"
            detail = f"actual={actual!r}"
        elif atype == "not-equals":
            actual = (
                json_path(parsed, assertion.get("path", "$"))
                if parsed is not None
                else output_text
            )
            status = "pass" if actual != assertion.get("value") else "fail"
            detail = f"actual={actual!r}"
        elif atype == "regex":
            status = (
                "pass"
                if re.search(str(assertion.get("pattern", "")), output_text)
                else "fail"
            )
        elif atype in {"is-json", "contains-json"}:
            status = "pass" if parsed is not None else "fail"
            detail = parse_error or ""
        elif atype == "required-fields":
            fields = assertion.get("fields") or []
            missing = [
                field for field in fields if json_path(parsed, f"$.{field}") is None
            ]
            status = "pass" if not missing else "fail"
            detail = f"missing={missing}" if missing else ""
        elif atype == "json-schema":
            errors = validate_schema_subset(parsed, assertion.get("schema") or {})
            status = "pass" if not errors else "fail"
            detail = "; ".join(errors)
        elif atype == "javascript":
            status, detail = evaluate_javascript_assertion(
                output_text, parsed, assertion
            )
        else:
            status = "unsupported"
            detail = f"unsupported assertion type: {atype}"

        results.append(
            {
                "type": atype,
                "status": status,
                "detail": detail,
                "weight": float(assertion.get("weight", 1.0)),
            }
        )
    return results


def evaluate_javascript_assertion(
    output_text: str,
    parsed: Any,
    assertion: dict[str, Any],
) -> tuple[str, str]:
    if not assertion.get("allow_code"):
        return "unsupported", "javascript assertion requires --allow-code"
    node = shutil.which("node")
    if not node:
        return "fail", "node executable not found for --allow-code javascript assertion"
    expression = str(assertion.get("value", "")).strip()
    if not expression:
        return "fail", "empty javascript assertion"
    script = """
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const output = input.output;
const json = input.json;
let result = false;
try {
  result = Boolean(eval(input.expression));
} catch (err) {
  console.error(err && err.message ? err.message : String(err));
  process.exit(2);
}
process.exit(result ? 0 : 1);
"""
    proc = subprocess.run(
        [node, "-e", script],
        input=json.dumps(
            {"output": output_text, "json": parsed, "expression": expression}
        ),
        text=True,
        capture_output=True,
        timeout=float(assertion.get("timeout_seconds", 5)),
        check=False,
    )
    if proc.returncode == 0:
        return "pass", "javascript assertion returned true"
    if proc.returncode == 1:
        return "fail", "javascript assertion returned false"
    detail = (proc.stderr or proc.stdout or f"node exited {proc.returncode}").strip()
    return "fail", detail[:500]


def validate_schema_subset(data: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(data, dict):
        return ["expected object"]
    if not isinstance(data, dict):
        return errors
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"missing required field {field}")
    props = schema.get("properties") or {}
    for field, spec in props.items():
        if field not in data:
            continue
        want = spec.get("type")
        got = data[field]
        if want == "string" and not isinstance(got, str):
            errors.append(f"{field} expected string")
        elif want == "number" and not isinstance(got, (int, float)):
            errors.append(f"{field} expected number")
        elif want == "array" and not isinstance(got, list):
            errors.append(f"{field} expected array")
        elif want == "object" and not isinstance(got, dict):
            errors.append(f"{field} expected object")
    return errors


def score_assertions(assertions: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(float(a.get("weight", 1.0)) for a in assertions)
    passed = sum(
        float(a.get("weight", 1.0)) for a in assertions if a["status"] == "pass"
    )
    score = passed / total if total else 0.0
    return {
        "score": round(score, 4),
        "passed": sum(1 for a in assertions if a["status"] == "pass"),
        "failed": sum(1 for a in assertions if a["status"] in {"fail", "unsupported"}),
        "unsupported": sum(1 for a in assertions if a["status"] == "unsupported"),
    }
