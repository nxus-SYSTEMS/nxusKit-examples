#!/usr/bin/env python3
"""Contract tests for the model research harness example."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_DIR = ROOT / "python"
if str(PY_DIR) not in sys.path:
    sys.path.insert(0, str(PY_DIR))

from harness.config import load_config  # noqa: E402


def run_py(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PY_DIR / "main.py"), *args],
        cwd=PY_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


def test_basic_mock_json_passes() -> None:
    proc = run_py(
        "--config",
        str(ROOT / "configs/nxuskit-harness-basic.yaml"),
        "--mode",
        "mock",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["final_status"] == "pass"
    assert report["capability_truth_table"][0]["harness_validated"] is True
    assert report["bayesian_confidence"]["mean_confidence"] > 0.5


def test_structured_output_prompt_declares_required_schema_fields() -> None:
    """Catches a Live prompt omitting fields enforced by its output assertion."""

    config = load_config(ROOT / "configs/nxuskit-harness-structured-output.yaml")
    test = config["tests"][0]
    prompt = test["prompt"]
    required = test["assertions"][0]["schema"]["required"]

    assert required == ["label", "confidence", "rationale"]
    assert all(field in prompt for field in required)
    assert "confidence as a number" in prompt


def test_promptfoo_basic_import_runs() -> None:
    proc = run_py(
        "--import-promptfoo", str(ROOT / "configs/promptfoo-basic.yaml"), "--json"
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["compatibility_report"]["status"] == "converted"
    assert report["final_status"] == "pass"


def test_promptfoo_requires_code_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "compat.json"
        proc = run_py(
            "--import-promptfoo",
            str(ROOT / "configs/promptfoo-requires-code.yaml"),
            "--compatibility-report",
            str(report_path),
            "--json",
        )
        assert proc.returncode == 0, proc.stderr
        compatibility = json.loads(report_path.read_text())
        assert compatibility["status"] == "requires_explicit_flag"
        assert compatibility["blocked_features"][0]["feature"] == "javascript_assertion"


def test_software_dev_scenarios_cover_required_types() -> None:
    proc = run_py(
        "--config", str(ROOT / "configs/nxuskit-harness-software-dev.yaml"), "--json"
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    got = {result["test_id"] for result in report["results"]}
    assert {
        "code-analysis",
        "bug-finding",
        "bugfixing",
        "code-generation",
        "refactoring",
        "code-review",
    } <= got


def test_bundled_mock_configs_pass() -> None:
    configs = [
        "nxuskit-harness-bayesian-confidence.yaml",
        "nxuskit-harness-bn-engine.yaml",
        "nxuskit-harness-clips-engine.yaml",
        "nxuskit-harness-clips-policy.yaml",
        "nxuskit-harness-lifecycle-policy.yaml",
        "nxuskit-harness-local-vs-cloud.yaml",
        "nxuskit-harness-matrix-template.yaml",
        "nxuskit-harness-native-ollama-template.yaml",
        "nxuskit-harness-structured-output.yaml",
    ]
    for config in configs:
        proc = run_py("--config", str(ROOT / "configs" / config), "--json")
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["final_status"] == "pass", config


def test_promptfoo_allow_code_runs_javascript_assertion() -> None:
    proc = run_py(
        "--import-promptfoo",
        str(ROOT / "configs/promptfoo-requires-code.yaml"),
        "--allow-code",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["final_status"] == "pass"
    assert (
        report["results"][0]["assertions"][0]["detail"]
        == "javascript assertion returned true"
    )


def test_external_command_requires_explicit_flag() -> None:
    proc = run_py(
        "--config",
        str(ROOT / "configs/nxuskit-harness-external-command-fixture.yaml"),
        "--json",
    )
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["final_status"] == "fail"
    assert report["results"][0]["metadata"]["requires_flag"] == "--allow-external"


def test_external_command_fixture_runs_with_flag() -> None:
    proc = run_py(
        "--config",
        str(ROOT / "configs/nxuskit-harness-external-command-fixture.yaml"),
        "--allow-external",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["final_status"] == "pass"
    got = {result["test_id"] for result in report["results"]}
    assert {
        "capabilities-fixture",
        "common-sense-fixture",
        "tool-intent-fixture",
        "safe-labs-fixture",
        "pipeline-fixture",
        "vision-fixture",
    } <= got


def test_only_test_filters_expensive_adapter_matrix() -> None:
    proc = run_py(
        "--config",
        str(ROOT / "configs/nxuskit-harness-external-command-fixture.yaml"),
        "--allow-external",
        "--only-test",
        "common-sense-fixture",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert [result["test_id"] for result in report["results"]] == [
        "common-sense-fixture"
    ]


def test_matrix_config_expands_variants() -> None:
    proc = run_py(
        "--config", str(ROOT / "configs/nxuskit-harness-matrix-template.yaml"), "--json"
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert len(report["results"]) == 4
    assert {
        "format-baseline-think-off",
        "format-baseline-think-low",
        "format-strict-think-off",
        "format-strict-think-low",
    } == {result["test_id"] for result in report["results"]}


def test_lifecycle_mutation_requires_separate_flag() -> None:
    proc = run_py(
        "--config",
        str(ROOT / "configs/nxuskit-harness-lifecycle-mutation-fixture.yaml"),
        "--allow-external",
        "--json",
    )
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert (
        report["results"][0]["metadata"]["requires_flag"]
        == "--allow-lifecycle-mutations"
    )

    proc = run_py(
        "--config",
        str(ROOT / "configs/nxuskit-harness-lifecycle-mutation-fixture.yaml"),
        "--allow-external",
        "--allow-lifecycle-mutations",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["final_status"] == "pass"


def main() -> int:
    tests = [name for name in globals() if name.startswith("test_")]
    failed = 0
    for name in sorted(tests):
        try:
            globals()[name]()
            print(f"ok {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
