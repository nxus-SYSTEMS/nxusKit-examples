#!/usr/bin/env python3
"""Contract tests for the common-sense guardrails example."""

from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY_DIR = ROOT / "python"
BASH_DIR = ROOT / "bash"
REPO = ROOT.parents[2]
MANIFEST = REPO / "conformance" / "examples_manifest.json"
SMOKE_MATRIX = REPO / "conformance" / "example_smoke_matrix.json"
SCENARIOS = ("car-wash", "coupon-stack", "pallet-door", "cold-chain")
CE_IDS = (
    "raw-baseline",
    "structured-facts",
    "clips-validation",
    "repair-packet",
    "corrected-answer",
)


def load_example_module():
    spec = importlib.util.spec_from_file_location("csg_main", PY_DIR / "main.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CSG = load_example_module()


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "NXUSKIT_PROVIDER",
        "NXUSKIT_MODEL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_HOST",
        "LMSTUDIO_BASE_URL",
        "NXUSKIT_LICENSE_TOKEN",
        "ENT_TOKEN_FILE",
    ):
        env.pop(key, None)
    return env


def run_py(
    *args: str, env: dict[str, str] | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PY_DIR / "main.py"), *args],
        cwd=cwd or PY_DIR,
        env=env or clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def run_json(*args: str) -> dict:
    proc = run_py(*args, "--json")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def load_expected(scenario: str) -> dict:
    return json.loads(
        (ROOT / "scenarios" / scenario / "expected-output.json").read_text()
    )


def assert_ce_report(report: dict, scenario: str) -> None:
    expected = load_expected(scenario)
    assert report["example"] == "common-sense-guardrails"
    assert report["scenario"] == scenario
    assert report["final_status"] == "pass"
    stage_ids = [stage["id"] for stage in report["stages"]]
    for stage_id in CE_IDS:
        assert stage_id in stage_ids
    assert expected["required_stage_ids"] == list(CE_IDS)
    clips = next(
        stage for stage in report["stages"] if stage["id"] == "clips-validation"
    )
    got_rule_ids = {finding["rule_id"] for finding in clips["output"]["findings"]}
    want_rule_ids = {finding["rule_id"] for finding in expected["expected_findings"]}
    assert want_rule_ids <= got_rule_ids
    corrected = next(
        stage for stage in report["stages"] if stage["id"] == "corrected-answer"
    )
    content = corrected["output"]["content"].lower()
    for token in expected["expected_correction_contains"]:
        assert token.lower() in content


def test_validate_scenarios() -> None:
    proc = run_py("--validate-scenarios")
    assert proc.returncode == 0, proc.stderr
    assert "valid" in proc.stdout


def test_all_scenarios_mock_ce() -> None:
    for scenario in SCENARIOS:
        report = run_json("--scenario", scenario, "--mode", "mock", "--stage", "ce")
        assert report["resolved_mode"] == "mock"
        assert all(stage["tier"] == "community" for stage in report["stages"])
        assert_ce_report(report, scenario)


def test_car_wash_repair_packet_and_order() -> None:
    report = run_json("--scenario", "car-wash", "--mode", "mock", "--stage", "ce")
    assert [stage["id"] for stage in report["stages"]] == list(CE_IDS)
    packet = next(
        stage for stage in report["stages"] if stage["id"] == "repair-packet"
    )["output"]
    assert packet["original_prompt"]
    assert packet["raw_response"]
    assert packet["extracted_facts"]["objects_required"]
    assert packet["findings"][0]["rule_id"] == "car-required-at-wash"
    assert "car" in packet["retry_prompt"].lower()


def test_all_scenarios_mock_pro_and_all() -> None:
    for scenario in SCENARIOS:
        pro = run_json("--scenario", scenario, "--mode", "mock", "--stage", "pro")
        assert len(pro["stages"]) == 1
        assert pro["stages"][0]["tier"] == "pro"
        assert pro["stages"][0]["source"] == "mock"
        assert pro["stages"][0]["output"]["entitlement_mode"] == "mock-fixture"
        combined = run_json("--scenario", scenario, "--mode", "mock", "--stage", "all")
        assert len(combined["stages"]) == 6
        assert combined["stages"][-1]["tier"] == "pro"


def test_simulated_live_all_skips_pro_without_entitlement() -> None:
    env = clean_env()
    env["NXUSKIT_COMMON_SENSE_SIMULATE_LIVE"] = "1"
    env["ENT_TOKEN_FILE"] = str(PY_DIR / ".no-license-token")
    for scenario in SCENARIOS:
        proc = run_py(
            "--scenario",
            scenario,
            "--mode",
            "live",
            "--stage",
            "all",
            "--json",
            env=env,
        )
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["resolved_mode"] == "live"
        assert report["final_status"] == "pass"
        assert report["stages"][0]["source"] == "live"
        assert report["stages"][-1]["tier"] == "pro"
        assert report["stages"][-1]["status"] == "skipped"
        assert report["stages"][-1]["output"]["entitlement_mode"] == "unavailable"


def test_auto_mode_falls_back_to_mock_without_provider() -> None:
    report = run_json("--scenario", "car-wash", "--mode", "auto", "--stage", "ce")
    assert report["mode"] == "auto"
    assert report["resolved_mode"] == "mock"
    assert "using checked-in fixtures" in report["mode_resolution"]["message"]
    assert all(stage["source"] == "mock" for stage in report["stages"])


def test_live_without_provider_fails_clearly() -> None:
    proc = run_py("--scenario", "car-wash", "--mode", "live", "--stage", "ce")
    assert proc.returncode != 0
    assert "live mode requires" in proc.stderr


def test_ollama_provider_uses_live_host_and_local_timeouts() -> None:
    calls: dict = {}

    class FakeProvider:
        @staticmethod
        def ollama(**kwargs):
            calls.update(kwargs)
            return object()

    original_module = sys.modules.get("nxuskit")
    fake_module = type(sys)("nxuskit")
    fake_module.Provider = FakeProvider
    sys.modules["nxuskit"] = fake_module

    original_env = os.environ.copy()
    try:
        os.environ["NXUSKIT_PROVIDER"] = "ollama"
        os.environ["NXUSKIT_MODEL"] = "llama3.1:8b"
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
        CSG.make_provider()
    finally:
        os.environ.clear()
        os.environ.update(original_env)
        if original_module is None:
            sys.modules.pop("nxuskit", None)
        else:
            sys.modules["nxuskit"] = original_module

    assert calls["model"] == "llama3.1:8b"
    assert calls["api_url"] == "http://127.0.0.1:11434"
    assert calls["timeout"] == 120.0
    assert calls["connect_timeout"] == 5.0
    assert calls["read_timeout"] == 120.0


def test_phase_specific_ollama_model_overrides_global_model() -> None:
    calls: list[dict] = []

    class FakeProvider:
        @staticmethod
        def ollama(**kwargs):
            calls.append(kwargs)
            return object()

    original_module = sys.modules.get("nxuskit")
    fake_module = type(sys)("nxuskit")
    fake_module.Provider = FakeProvider
    sys.modules["nxuskit"] = fake_module

    original_env = os.environ.copy()
    try:
        os.environ["NXUSKIT_PROVIDER"] = "ollama"
        os.environ["NXUSKIT_MODEL"] = "llama3.2"
        os.environ["NXUSKIT_COMMON_SENSE_FACTS_MODEL"] = "qwen3:4b"
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
        CSG.make_provider("baseline")
        CSG.make_provider("facts")
        CSG.make_provider("repair")
    finally:
        os.environ.clear()
        os.environ.update(original_env)
        if original_module is None:
            sys.modules.pop("nxuskit", None)
        else:
            sys.modules["nxuskit"] = original_module

    assert [call["model"] for call in calls] == ["llama3.2", "qwen3:4b", "llama3.2"]


def test_structured_json_accepts_pure_json_without_warning() -> None:
    content = json.dumps(
        {
            "goal": "wash car",
            "candidate_actions": [],
            "objects_required": [],
            "objects_moved": [],
            "resources": [],
            "constraints": [],
            "policy_context": {},
            "confidence": 0.9,
        }
    )
    facts, warning = CSG.parse_facts_response(content)
    assert facts["goal"] == "wash car"
    assert warning is None


def test_structured_json_extracts_embedded_fence_with_warning() -> None:
    content = """Here are the extracted JSON facts:

```json
{
  "goal": "wash car",
  "candidate_actions": [],
  "objects_required": [],
  "objects_moved": [],
  "resources": [],
  "constraints": [],
  "policy_context": {},
  "confidence": 0.8
}
```

Let me know if you need anything else.
"""
    facts, warning = CSG.parse_facts_response(content)
    assert facts["goal"] == "wash car"
    assert warning is not None
    assert "wrapped JSON in prose" in warning


def test_structured_json_errors_when_no_json_is_extractable() -> None:
    try:
        CSG.parse_facts_response("I found the facts, but I will not return JSON.")
    except CSG.StructuredJsonError as exc:
        assert "no valid JSON object" in str(exc)
    else:
        raise AssertionError("expected StructuredJsonError")


def test_live_mode_falls_back_when_structured_fact_json_invalid() -> None:
    scenario = CSG.load_scenario("car-wash")
    responses = iter(
        [
            "Walk to the car wash because it is nearby.",
            "I found the facts, but I will not return JSON.",
            "Still no JSON object here.",
            "Drive the car to the car wash, or walk only if the car is already there.",
        ]
    )

    original_make_provider = CSG.make_provider
    original_provider_chat = CSG.provider_chat
    original_live_clips_findings = CSG.live_clips_findings
    try:
        CSG.make_provider = lambda *_args: object()
        CSG.provider_chat = lambda *_args, **_kwargs: next(responses)
        CSG.live_clips_findings = lambda loaded, facts: {
            "findings": CSG.expected_findings(loaded["expected"], facts)
        }
        stages = CSG.live_ce_stages(scenario, allow_fixture_fallback=False)
    finally:
        CSG.make_provider = original_make_provider
        CSG.provider_chat = original_provider_chat
        CSG.live_clips_findings = original_live_clips_findings

    structured = next(stage for stage in stages if stage["id"] == "structured-facts")
    assert structured["source"] == "mock"
    assert structured["status"] == "fail"
    assert "using checked-in fact fixture" in structured["message"]
    assert structured["output"] == scenario["facts"]


def test_structured_json_rejects_wrong_fact_shape() -> None:
    content = json.dumps(
        {
            "goal": "Get a car washed",
            "candidate_actions": [{"name": "Walk or jog"}],
            "objects_required": {"location1": ["car"], "location2": []},
            "objects_moved": {"location1": ["car"], "location2": []},
            "resources": {"energy": "walking"},
            "constraints": [{"type": "distance", "value": "50 meters"}],
            "policy_context": "car wash",
            "confidence": 0.8,
        }
    )
    try:
        CSG.parse_facts_response(content)
    except CSG.StructuredJsonError as exc:
        message = str(exc)
        assert "objects_required" in message
        assert "policy_context" in message
    else:
        raise AssertionError("expected StructuredJsonError")


def test_missing_artifact_names_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        copy_root = scratch / "common-sense-guardrails"
        shutil.copytree(ROOT, copy_root)
        missing = copy_root / "scenarios" / "car-wash" / "mock-facts.json"
        missing.unlink()
        proc = subprocess.run(
            [
                sys.executable,
                str(copy_root / "python" / "main.py"),
                "--validate-scenarios",
            ],
            cwd=copy_root / "python",
            env=clean_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode != 0
        assert "mock-facts.json" in proc.stderr


def test_temporary_scenario_skeleton_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        skeleton = Path(tmp) / "scratch-scenario"
        shutil.copytree(ROOT / "scenarios" / "car-wash", skeleton)
        problem = json.loads((skeleton / "problem.json").read_text())
        problem["id"] = "scratch-scenario"
        (skeleton / "problem.json").write_text(
            json.dumps(problem, indent=2, sort_keys=True) + "\n"
        )
        expected = json.loads((skeleton / "expected-output.json").read_text())
        expected["scenario"] = "scratch-scenario"
        (skeleton / "expected-output.json").write_text(
            json.dumps(expected, indent=2, sort_keys=True) + "\n"
        )

        for filename in (
            "problem.json",
            "expected-output.json",
            "rules.clp",
            "mock-baseline.json",
            "mock-facts.json",
            "mock-repair.json",
            "mock-corrected.json",
        ):
            assert (skeleton / filename).is_file()
        assert "{findings}" in problem["repair_template"]
        assert set(CE_IDS) <= set(expected["required_stage_ids"])


def test_no_direct_provider_sdk_imports() -> None:
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(?:openai|anthropic|ollama)\b", re.MULTILINE
    )
    for path in (PY_DIR / "main.py", BASH_DIR / "main.sh"):
        text = path.read_text()
        assert not pattern.search(text), f"direct provider SDK import in {path}"


def test_manifest_tier_profile_contract() -> None:
    manifest = json.loads(MANIFEST.read_text())
    matches = [
        ex for ex in manifest["examples"] if ex["name"] == "common-sense-guardrails"
    ]
    assert len(matches) == 1
    ex = matches[0]
    assert ex["tier"] == "community"
    assert ex["tier"] != "mixed"
    assert ex["difficulty"] == "advanced"
    assert ex["languages"] == ["python", "bash"]
    assert ex["edition_note"]
    assert len(ex["scenarios"]) == 4
    profile = ex["tier_profile"]
    assert profile["minimum_tier"] == "community"
    assert "community" in profile["tiers"]
    assert any(
        stage["id"] == "ce" and not stage["requires_entitlement"]
        for stage in profile["stages"]
    )
    assert any(
        stage["tier"] == "pro" and stage["requires_entitlement"]
        for stage in profile["stages"]
    )


def test_smoke_matrix_stage_rows() -> None:
    matrix = json.loads(SMOKE_MATRIX.read_text())
    rows = [
        row for row in matrix["runs"] if row["example"] == "common-sense-guardrails"
    ]
    ids = {row["id"] for row in rows}
    assert "common-sense-guardrails|python|ce" in ids
    assert "common-sense-guardrails|python|pro" in ids
    assert "common-sense-guardrails|bash|ce" in ids
    assert "common-sense-guardrails|bash|pro" in ids
    for row in rows:
        assert row["tier"] == "community"
        assert row["stage"] in {"ce", "pro"}
        assert row["requires_pro"] is False


def test_readme_authoring_sections() -> None:
    readme = (ROOT / "README.md").read_text()
    for heading in (
        "## Edition",
        "## Pro Enhancement Path",
        "## Adding a Scenario",
        "## Scenario Data Contract",
        "## Scope Exclusions",
        "## Public Inspiration",
    ):
        assert heading in readme
    for filename in (
        "problem.json",
        "expected-output.json",
        "rules.clp",
        "mock-baseline.json",
        "mock-facts.json",
        "mock-repair.json",
        "mock-corrected.json",
    ):
        assert filename in readme


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
