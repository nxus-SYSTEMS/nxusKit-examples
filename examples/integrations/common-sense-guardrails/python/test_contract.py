#!/usr/bin/env python3
# fmt: off
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
BN_SCENARIOS = ("coupon-stack", "cold-chain")
NO_BN_SCENARIOS = ("car-wash", "pallet-door")
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
        "NXUSKIT_COMMON_SENSE_FIXTURE_LLM",
        "NXUSKIT_COMMON_SENSE_SIMULATE_LIVE",
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


def scenario_pro_engine(scenario: str) -> str:
    problem = json.loads((ROOT / "scenarios" / scenario / "problem.json").read_text())
    return problem.get("pro_stage", {}).get("engine", "solver")


def scenario_pro_stage_id(scenario: str) -> str:
    problem = json.loads((ROOT / "scenarios" / scenario / "problem.json").read_text())
    pro_stage = problem.get("pro_stage", {})
    return pro_stage.get(
        "id", "zen-policy" if scenario_pro_engine(scenario) == "zen" else "solver-proof"
    )


def scenario_supports_bn(scenario: str) -> bool:
    problem = json.loads((ROOT / "scenarios" / scenario / "problem.json").read_text())
    return bool(problem.get("bn_stage"))


def expected_auto_selection(scenario: str) -> list[str]:
    selected = ["clips", scenario_pro_engine(scenario)]
    if scenario_supports_bn(scenario):
        selected.append("bn")
    return selected


def stage_by_id(report: dict, stage_id: str) -> dict:
    return next(stage for stage in report["stages"] if stage["id"] == stage_id)


def assert_ce_report(report: dict, scenario: str) -> None:
    expected = load_expected(scenario)
    assert report["example"] == "common-sense-guardrails"
    assert report["scenario"] == scenario
    assert report["final_status"] == "pass"
    assert report["guardrail_selection"]["selected"] == ["clips"]
    assert report["max_repair_attempts"] == 3
    stage_ids = [stage["id"] for stage in report["stages"]]
    for stage_id in CE_IDS:
        assert stage_id in stage_ids
    assert expected["required_stage_ids"] == list(CE_IDS)
    clips = stage_by_id(report, "clips-validation")
    got_rule_ids = {
        finding["rule_id"]
        for finding in clips["output"]["attempts"][0]["findings"]
    }
    want_rule_ids = {finding["rule_id"] for finding in expected["expected_findings"]}
    assert want_rule_ids <= got_rule_ids
    assert all(
        finding["status"] == "pass" for finding in clips["output"]["findings"]
    )
    corrected = stage_by_id(report, "corrected-answer")
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
    assert packet["findings"][0]["mechanism"] == "clips"
    assert "car" in packet["retry_prompt"].lower()


def test_all_scenarios_mock_pro_and_all() -> None:
    for scenario in SCENARIOS:
        engine = scenario_pro_engine(scenario)
        pro_stage_id = scenario_pro_stage_id(scenario)
        pro = run_json("--scenario", scenario, "--mode", "mock", "--stage", "pro")
        assert [stage["id"] for stage in pro["stages"]] == [
            "raw-baseline",
            "structured-facts",
            pro_stage_id,
            "repair-packet",
            "corrected-answer",
        ]
        assert pro["guardrail_selection"]["selected"] == [engine]
        pro_stage = next(stage for stage in pro["stages"] if stage["id"] == pro_stage_id)
        assert pro_stage["tier"] == "pro"
        assert pro_stage["source"] == "mock"
        assert pro_stage["output"]["mechanism"] == engine
        assert pro_stage["output"]["attempts"][0]["status"] == "fail"
        assert pro_stage["output"]["attempts"][1]["status"] == "pass"
        assert pro_stage["output"]["attempts"][0]["findings"][0]["evidence"][
            "runtime_executed"
        ] is False

        combined = run_json("--scenario", scenario, "--mode", "mock", "--stage", "all")
        expected_stage_count = 7 if scenario_supports_bn(scenario) else 6
        assert len(combined["stages"]) == expected_stage_count
        assert combined["guardrail_selection"]["selected"] == expected_auto_selection(scenario)
        combined_pro_stage = stage_by_id(combined, pro_stage_id)
        assert combined_pro_stage["tier"] == "pro"
        if scenario_supports_bn(scenario):
            combined_bn_stage = stage_by_id(combined, "bn-risk")
            assert combined_bn_stage["tier"] == "community"
            assert combined_bn_stage["output"]["mechanism"] == "bn"
            assert combined_bn_stage["output"]["attempts"][0]["status"] == "fail"
            assert combined_bn_stage["output"]["attempts"][1]["status"] == "pass"
        assert combined["stages"][-1]["id"] == "corrected-answer"
        assert combined["stages"][-1]["tier"] == "community"


def test_bn_guardrails_selected_only_for_uncertainty_scenarios() -> None:
    for scenario in BN_SCENARIOS:
        report = run_json("--scenario", scenario, "--mode", "mock", "--guardrails", "bn")
        assert report["guardrail_selection"]["selected"] == ["bn"]
        assert [stage["id"] for stage in report["stages"]] == [
            "raw-baseline",
            "structured-facts",
            "bn-risk",
            "repair-packet",
            "corrected-answer",
        ]
        bn_stage = stage_by_id(report, "bn-risk")
        assert bn_stage["label"] == "Bayesian risk / confidence"
        assert bn_stage["tier"] == "community"
        assert bn_stage["source"] == "mock"
        assert bn_stage["output"]["mechanism"] == "bn"
        assert bn_stage["output"]["attempts"][0]["status"] == "fail"
        assert bn_stage["output"]["attempts"][1]["status"] == "pass"
        first_finding = bn_stage["output"]["attempts"][0]["findings"][0]
        assert first_finding["mechanism"] == "bn"
        assert first_finding["status"] == "fail"
        assert first_finding["evidence"]["query_node"] == "needs_review"
        assert first_finding["evidence"]["runtime_executed"] is False
        repair = stage_by_id(report, "repair-packet")["output"]
        assert [finding["mechanism"] for finding in repair["findings"]] == ["bn"]

    for scenario in NO_BN_SCENARIOS:
        proc = run_py("--scenario", scenario, "--mode", "mock", "--guardrails", "bn", "--json")
        assert proc.returncode != 0
        assert "does not support BN" in proc.stderr


def test_combined_bn_guardrails_and_auto_selection() -> None:
    for scenario in BN_SCENARIOS:
        engine = scenario_pro_engine(scenario)
        for requested in ("clips,bn", f"clips,{engine},bn"):
            report = run_json("--scenario", scenario, "--mode", "mock", "--guardrails", requested)
            assert report["guardrail_selection"]["selected"] == requested.split(",")
            assert stage_by_id(report, "clips-validation")["output"]["mechanism"] == "clips"
            assert stage_by_id(report, "bn-risk")["output"]["mechanism"] == "bn"
            if engine in requested.split(","):
                assert stage_by_id(report, scenario_pro_stage_id(scenario))["output"]["mechanism"] == engine

        auto = run_json("--scenario", scenario, "--mode", "mock", "--guardrails", "auto")
        assert auto["guardrail_selection"]["selected"] == expected_auto_selection(scenario)
        assert "bn-risk" in [stage["id"] for stage in auto["stages"]]

    for scenario in NO_BN_SCENARIOS:
        auto = run_json("--scenario", scenario, "--mode", "mock", "--guardrails", "auto")
        assert auto["guardrail_selection"]["selected"] == expected_auto_selection(scenario)
        assert "bn-risk" not in [stage["id"] for stage in auto["stages"]]


def test_simulated_live_all_runs_fixture_backed_pro_shape() -> None:
    env = clean_env()
    env["NXUSKIT_COMMON_SENSE_SIMULATE_LIVE"] = "1"
    env["ENT_TOKEN_FILE"] = str(PY_DIR / ".no-license-token")
    for scenario in SCENARIOS:
        engine = scenario_pro_engine(scenario)
        pro_stage_id = "zen-policy" if engine == "zen" else "solver-proof"
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
        assert report["guardrail_selection"]["selected"] == expected_auto_selection(scenario)
        pro_stage = stage_by_id(report, pro_stage_id)
        assert pro_stage["tier"] == "pro"
        assert pro_stage["status"] == "pass"
        assert pro_stage["output"]["attempts"][0]["findings"][0]["evidence"][
            "runtime_executed"
        ] is False


def test_live_pro_adapters_use_nxuskit_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        fake_cli = scratch / "nxuskit-cli"
        log = scratch / "cli.log"
        fake_cli.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
sub="${2:-}"
shift 2 || true
input=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input|-i) input="${2:-}"; shift 2 ;;
    --output|-o) output="${2:-}"; shift 2 ;;
    --format|-f) shift 2 ;;
    *) shift ;;
  esac
done
printf '%s %s\\n' "$cmd" "$sub" >> "$NXUSKIT_FAKE_CLI_LOG"
if [[ "$cmd $sub" == "solver solve" ]]; then
  grep -q 'required_object_present_after_action' "$input"
  printf '{"result":{"satisfiable":false}}\\n' > "$output"
elif [[ "$cmd $sub" == "zen eval" ]]; then
  grep -q 'discount_count' "$input"
  printf '{"result":{"output":{"allowed":false,"decision":"rejected","repair_hint":"choose one eligible promotion"}}}\\n' > "$output"
elif [[ "$cmd $sub" == "bn infer" ]]; then
  grep -q 'needs_review' "$input"
  printf '{"result":{"posteriors":{"needs_review":{"yes":0.96,"no":0.04}}}}\\n' > "$output"
else
  echo "unexpected command: $cmd $sub" >&2
  exit 9
fi
""",
            encoding="utf-8",
        )
        fake_cli.chmod(0o755)

        original_env = os.environ.copy()
        try:
            os.environ["NXUSKIT_CLI"] = str(fake_cli)
            os.environ["NXUSKIT_FAKE_CLI_LOG"] = str(log)
            car = CSG.load_scenario("car-wash")
            coupon = CSG.load_scenario("coupon-stack")
            solver_findings = CSG.live_solver_findings(car, car["facts"])
            zen_findings = CSG.live_zen_findings(coupon, coupon["facts"])
            bn_findings = CSG.live_bn_findings(coupon, coupon["facts"])
            commands = log.read_text().splitlines()
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    assert solver_findings[0]["mechanism"] == "solver"
    assert solver_findings[0]["status"] == "fail"
    assert solver_findings[0]["evidence"]["runtime_executed"] is True
    assert zen_findings[0]["mechanism"] == "zen"
    assert zen_findings[0]["status"] == "fail"
    assert zen_findings[0]["evidence"]["runtime_executed"] is True
    assert bn_findings[0]["mechanism"] == "bn"
    assert bn_findings[0]["status"] == "fail"
    assert bn_findings[0]["evidence"]["runtime_executed"] is True
    assert commands == ["solver solve", "zen eval", "bn infer"]


def test_fixture_llm_live_pro_loop_uses_nxuskit_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        fake_cli = scratch / "nxuskit-cli"
        log = scratch / "cli.log"
        fake_cli.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
sub="${2:-}"
shift 2 || true
input=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input|-i) input="${2:-}"; shift 2 ;;
    --output|-o) output="${2:-}"; shift 2 ;;
    --format|-f) shift 2 ;;
    *) shift ;;
  esac
done
printf '%s %s\\n' "$cmd" "$sub" >> "$NXUSKIT_FAKE_CLI_LOG"
if [[ "$cmd $sub" == "solver solve" ]]; then
  if jq -e '.variables[] | select(.name == "required_object_present_after_action") | .domain.min == 1' "$input" >/dev/null; then
    printf '{"result":{"satisfiable":true}}\\n' > "$output"
  else
    printf '{"result":{"satisfiable":false}}\\n' > "$output"
  fi
elif [[ "$cmd $sub" == "zen eval" ]]; then
  if jq -e '(.input.discount_count // 99) <= 1 and (.input.combined_margin_percent // -99) >= 0' "$input" >/dev/null; then
    printf '{"result":{"output":{"allowed":true,"decision":"allow_single_discount"}}}\\n' > "$output"
  else
    printf '{"result":{"output":{"allowed":false,"decision":"deny_stack","repair_hint":"choose one eligible promotion"}}}\\n' > "$output"
  fi
elif [[ "$cmd $sub" == "bn infer" ]]; then
  if jq -e '.evidence.discount_count_bucket == "low" and .evidence.margin_floor_breach == "no" and .evidence.non_stackable_conflict == "no"' "$input" >/dev/null; then
    printf '{"result":{"posteriors":{"needs_review":{"yes":0.22,"no":0.78}}}}\\n' > "$output"
  else
    printf '{"result":{"posteriors":{"needs_review":{"yes":0.96,"no":0.04}}}}\\n' > "$output"
  fi
else
  echo "unexpected command: $cmd $sub" >&2
  exit 9
fi
""",
            encoding="utf-8",
        )
        fake_cli.chmod(0o755)
        env = clean_env()
        env["NXUSKIT_CLI"] = str(fake_cli)
        env["NXUSKIT_FAKE_CLI_LOG"] = str(log)
        env["NXUSKIT_COMMON_SENSE_FIXTURE_LLM"] = "1"

        solver_proc = run_py(
            "--scenario",
            "car-wash",
            "--mode",
            "live",
            "--stage",
            "pro",
            "--json",
            env=env,
        )
        zen_proc = run_py(
            "--scenario",
            "coupon-stack",
            "--mode",
            "live",
            "--stage",
            "pro",
            "--json",
            env=env,
        )
        bn_proc = run_py(
            "--scenario",
            "coupon-stack",
            "--mode",
            "live",
            "--guardrails",
            "bn",
            "--json",
            env=env,
        )
        commands = log.read_text().splitlines()

    assert solver_proc.returncode == 0, solver_proc.stderr
    assert zen_proc.returncode == 0, zen_proc.stderr
    assert bn_proc.returncode == 0, bn_proc.stderr
    solver = json.loads(solver_proc.stdout)
    zen = json.loads(zen_proc.stdout)
    bn = json.loads(bn_proc.stdout)
    solver_stage = next(stage for stage in solver["stages"] if stage["id"] == "solver-proof")
    zen_stage = next(stage for stage in zen["stages"] if stage["id"] == "zen-policy")
    bn_stage = stage_by_id(bn, "bn-risk")
    assert solver["mode_resolution"]["message"].startswith("fixture LLM answers")
    assert solver_stage["source"] == "live"
    assert solver_stage["output"]["attempts"][0]["status"] == "fail"
    assert solver_stage["output"]["attempts"][1]["status"] == "pass"
    assert solver_stage["output"]["attempts"][0]["findings"][0]["evidence"][
        "runtime_executed"
    ] is True
    assert zen_stage["source"] == "live"
    assert zen_stage["output"]["attempts"][0]["status"] == "fail"
    assert zen_stage["output"]["attempts"][1]["status"] == "pass"
    assert zen_stage["output"]["attempts"][0]["findings"][0]["evidence"][
        "runtime_executed"
    ] is True
    assert bn_stage["source"] == "live"
    assert bn_stage["output"]["attempts"][0]["status"] == "fail"
    assert bn_stage["output"]["attempts"][1]["status"] == "pass"
    assert bn_stage["output"]["attempts"][0]["findings"][0]["evidence"][
        "runtime_executed"
    ] is True
    assert commands == [
        "solver solve",
        "solver solve",
        "zen eval",
        "zen eval",
        "bn infer",
        "bn infer",
    ]


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


def test_default_mode_is_live_and_fails_without_provider() -> None:
    proc = run_py("--scenario", "car-wash", "--stage", "ce")
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


def test_clips_slot_values_accept_string_and_dict() -> None:
    encoded = json.dumps(
        {
            "status": {"value": "fail"},
            "rule-id": {"value": "car-required-at-wash"},
        }
    )
    parsed = CSG.normalize_clips_slot_values(encoded)
    assert parsed["status"]["value"] == "fail"
    direct = CSG.normalize_clips_slot_values({"status": "pass"})
    assert direct["status"] == "pass"


def test_live_structured_facts_requests_json_response_format() -> None:
    captured: list[object] = []

    class FakeResponseFormat:
        JSON = object()

    original_module = sys.modules.get("nxuskit")
    fake_module = type(sys)("nxuskit")
    fake_module.ResponseFormat = FakeResponseFormat
    sys.modules["nxuskit"] = fake_module

    original_provider_chat = CSG.provider_chat
    try:
        CSG.provider_chat = lambda *_args, **kwargs: (
            captured.append(kwargs.get("response_format"))
            or json.dumps(
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
        )
        facts, status, _message = CSG.live_structured_facts(object(), "extract")
    finally:
        CSG.provider_chat = original_provider_chat
        if original_module is None:
            sys.modules.pop("nxuskit", None)
        else:
            sys.modules["nxuskit"] = original_module

    assert facts["goal"] == "wash car"
    assert status == "pass"
    assert captured == [FakeResponseFormat.JSON]


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
            "mock-corrected-facts.json",
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
    assert ex["tech_tags"] == ["LLM", "CLIPS", "Solver", "BN", "ZEN"]
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
        stage["id"] == "bn-risk"
        and stage["tier"] == "community"
        and not stage["requires_entitlement"]
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
    assert "common-sense-guardrails|python|bn" in ids
    assert "common-sense-guardrails|bash|ce" in ids
    assert "common-sense-guardrails|bash|pro" in ids
    assert "common-sense-guardrails|bash|bn" in ids
    for row in rows:
        assert row["tier"] == "community"
        assert row["stage"] in {"ce", "pro", "bn"}
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
        "mock-corrected-facts.json",
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
