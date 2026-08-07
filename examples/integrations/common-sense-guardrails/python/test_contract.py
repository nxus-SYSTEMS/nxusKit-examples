#!/usr/bin/env python3
# fmt: off
"""Contract tests for the common-sense guardrails example."""

from __future__ import annotations

import json
import importlib.util
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import jsonschema

from llm_interactions import LLMCallContext, LLMInteractionRecorder
from nxuskit_cli_provider import NxuskitCliOllamaProvider
from run_events import RunEventEmitter


ROOT = Path(__file__).resolve().parents[1]
PY_DIR = ROOT / "python"
BASH_DIR = ROOT / "bash"
REPO = ROOT.parents[2]
MANIFEST = REPO / "conformance" / "examples_manifest.json"
SMOKE_MATRIX = REPO / "conformance" / "example_smoke_matrix.json"
REASONING_RECORD_SCHEMA = ROOT / "schemas" / "reasoning-record.schema.json"
RUN_OUTPUT_SCHEMA = ROOT / "schemas" / "run-output.schema.json"
PRIVATE_REASONING_RECORD_SCHEMA = (
    REPO
    / "specs"
    / "012-marimo-reasoning-lab-v105"
    / "contracts"
    / "reasoning-record.schema.json"
)
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


def load_core_module():
    spec = importlib.util.spec_from_file_location(
        "csg_guardrail_core", PY_DIR / "guardrail_core.py"
    )
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
        "GROQ_API_KEY",
        "XAI_API_KEY",
        "OLLAMA_HOST",
        "LMSTUDIO_BASE_URL",
        "NXUSKIT_LICENSE_TOKEN",
        "ENT_TOKEN_FILE",
        "NXUSKIT_COMMON_SENSE_FIXTURE_LLM",
        "NXUSKIT_COMMON_SENSE_SIMULATE_LIVE",
        "NXUSKIT_COMMON_SENSE_OLLAMA_READ_TIMEOUT_SECONDS",
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


def run_bash_json(*args: str) -> dict[str, object]:
    proc = subprocess.run(
        ["bash", str(BASH_DIR / "main.sh"), *args, "--json"],
        cwd=BASH_DIR,
        env=clean_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def validate_run_output(report: dict[str, object]) -> None:
    jsonschema.Draft202012Validator(
        json.loads(RUN_OUTPUT_SCHEMA.read_text(encoding="utf-8"))
    ).validate(report)


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


@pytest.mark.parametrize(
    ("case", "resources"),
    [
        ("boolean id", [{"id": True, "type": "coupon", "stackable": False}]),
        ("number id", [{"id": 1, "type": "coupon", "stackable": False}]),
        ("array id", [{"id": [], "type": "coupon", "stackable": False}]),
        ("object id", [{"id": {}, "type": "coupon", "stackable": False}]),
        ("null id", [{"id": None, "type": "coupon", "stackable": False}]),
        ("missing stackable", [{"id": "welcome-25", "type": "coupon"}]),
        (
            "nonboolean stackable",
            [{"id": "welcome-25", "type": "coupon", "stackable": "false"}],
        ),
        ("missing type", [{"id": "welcome-25", "stackable": False}]),
        ("nonstring type", [{"id": "welcome-25", "type": 1, "stackable": False}]),
        ("empty resources", []),
    ],
)
def test_coupon_required_shape_rejects_malformed_resources(
    case: str, resources: list[object]
) -> None:
    """Documents the typed resource boundary already enforced by Python live extraction."""

    scenario = CSG.load_scenario("coupon-stack")
    facts = json.loads(json.dumps(scenario["facts"]))
    facts["resources"] = resources

    errors = CSG.validate_facts_shape(facts, scenario["facts"])

    assert errors, f"Python required-shape validator accepted {case}"


def test_all_scenarios_mock_ce() -> None:
    for scenario in SCENARIOS:
        report = run_json("--scenario", scenario, "--mode", "mock", "--stage", "ce")
        assert report["resolved_mode"] == "mock"
        assert all(stage["tier"] == "community" for stage in report["stages"])
        assert_ce_report(report, scenario)


def test_canonical_reasoning_record_is_deterministic_and_shared() -> None:
    core = load_core_module()
    report = CSG.build_report("cold-chain", "mock", "ce")
    record = core.reasoning_record_from_report(report)

    assert record == core.reasoning_record_from_report(report)
    assert CSG.build_reasoning_record("cold-chain", "mock", "ce") == record
    assert json.loads(REASONING_RECORD_SCHEMA.read_text())["$id"].endswith(
        "reasoning-record-v1.json"
    )
    assert record["schema_version"] == "1.0.0"
    assert record["record_id"].startswith("rr-")
    assert len(record["input_sha256"]) == 64
    assert record["scenario"] == {
        "id": "cold-chain",
        "label": "cold-chain",
        "synthetic": True,
    }
    assert record["provenance"]["mode"] == "fixture"
    assert record["provenance"]["community_complete"] is True
    assert {mechanism["id"] for mechanism in record["mechanisms"]} == {"clips"}
    assert record["mechanisms"][0]["runtime_executed"] is False
    assert record["facts"]
    assert record["findings"]
    assert record["evidence"]
    assert record["attempts"]
    assert record["final"]["review_disposition"] == "complete"


def test_public_reasoning_record_schema_matches_private_contract_when_present() -> None:
    if PRIVATE_REASONING_RECORD_SCHEMA.exists():
        public_schema = json.loads(REASONING_RECORD_SCHEMA.read_text(encoding="utf-8"))
        private_schema = json.loads(
            PRIVATE_REASONING_RECORD_SCHEMA.read_text(encoding="utf-8")
        )
        assert public_schema == private_schema, (
            "public reasoning-record schema differs semantically from the private "
            "Spec 012 contract"
        )


def test_reasoning_record_attempt_status_aggregates_facts_and_engines() -> None:
    core = load_core_module()
    report = {
        "example": "common-sense-guardrails",
        "scenario": "car-wash",
        "mode": "live",
        "resolved_mode": "live",
        "requested_stage": "all",
        "requested_guardrails": "clips,solver",
        "max_repair_attempts": 3,
        "guardrail_selection": {"selected": ["clips", "solver"]},
        "final_status": "fail",
        "summary": "Run completed with failures.",
        "stages": [
            {
                "id": "structured-facts",
                "source": "live",
                "output": {
                    "current": {"goal": "wash-car"},
                    "attempts": [
                        {
                            "attempt": 1,
                            "status": "pass",
                            "facts": {"step": 1},
                            "input_sha256": "1" * 64,
                        },
                        {
                            "attempt": 2,
                            "status": "pass",
                            "facts": {"step": 2},
                            "input_sha256": "2" * 64,
                        },
                        {
                            "attempt": 3,
                            "status": "pass",
                            "facts": {"step": 3},
                            "input_sha256": "3" * 64,
                        },
                    ],
                },
            },
            {
                "id": "clips-validation",
                "tier": "community",
                "source": "live",
                "output": {
                    "mechanism": "clips",
                    "attempts": [
                        {"attempt": 1, "status": "fail", "findings": []},
                        {"attempt": 2, "status": "fail", "findings": []},
                        {"attempt": 3, "status": "fail", "findings": []},
                    ],
                },
            },
            {
                "id": "solver-proof",
                "tier": "pro",
                "source": "live",
                "output": {
                    "mechanism": "solver",
                    "attempts": [
                        {"attempt": 1, "status": "fail", "findings": []},
                        {"attempt": 2, "status": "pass", "findings": []},
                        {"attempt": 3, "status": "fail", "findings": []},
                    ],
                },
            },
        ],
    }

    record = core.reasoning_record_from_report(report)

    assert [item["status"] for item in record["attempts"]] == [
        "fail",
        "fail",
        "fail",
    ]
    assert [item["input_sha256"] for item in record["attempts"]] == [
        "1" * 64,
        "2" * 64,
        "3" * 64,
    ]
    assert record["attempts"][1]["repair_from_attempt"] == 1
    assert record["attempts"][2]["repair_from_attempt"] == 2


def test_repaired_attempts_hash_their_actual_evaluation_inputs() -> None:
    record = CSG.build_reasoning_record("car-wash", "mock", None, "clips", 3)

    assert [item["status"] for item in record["attempts"]] == ["fail", "pass"]
    assert record["attempts"][0]["input_sha256"] != record["attempts"][1][
        "input_sha256"
    ]
    assert record["attempts"][1]["repair_from_attempt"] == 1


def test_reasoning_record_attempt_is_unavailable_when_no_engine_evaluates() -> None:
    core = load_core_module()
    report = {
        "example": "common-sense-guardrails",
        "scenario": "car-wash",
        "mode": "fixture",
        "resolved_mode": "mock",
        "guardrail_selection": {"selected": ["solver"]},
        "final_status": "fail",
        "stages": [
            {
                "id": "structured-facts",
                "source": "mock",
                "output": {
                    "current": {"goal": "wash-car"},
                    "attempts": [
                        {
                            "attempt": 1,
                            "status": "pass",
                            "facts": {"goal": "wash-car"},
                            "input_sha256": "a" * 64,
                        }
                    ],
                },
            },
            {
                "id": "solver-proof",
                "tier": "pro",
                "source": "mock",
                "output": {
                    "mechanism": "solver",
                    "attempts": [
                        {"attempt": 1, "status": "unavailable", "findings": []}
                    ],
                },
            },
        ],
    }

    record = core.reasoning_record_from_report(report)

    assert record["attempts"][0]["status"] == "unavailable"


def test_fixture_loop_emits_ordered_attempt_and_repair_events() -> None:
    events = []

    CSG.build_reasoning_record(
        "car-wash",
        "mock",
        None,
        "clips",
        3,
        event_sink=events.append,
        utcnow=lambda: datetime(
            2026, 8, 3, 22, 24, 18, 270_000, tzinfo=timezone.utc
        ),
    )

    assert [(item["category"], item["status"]) for item in events] == [
        ("run", "started"),
        ("facts", "started"),
        ("facts", "completed"),
        ("engine", "started"),
        ("engine", "rejected"),
        ("run", "rejected"),
        ("repair", "completed"),
        ("repair", "retry"),
        ("facts", "started"),
        ("facts", "completed"),
        ("engine", "started"),
        ("engine", "accepted"),
        ("run", "accepted"),
        ("run", "accepted"),
    ]
    assert [item["message"] for item in events] == [
        "Analysis started for car-wash.",
        "Extracting structured facts for response attempt 1.",
        "Structured facts extracted from response attempt 1.",
        "Evaluating Community CLIPS validation for response attempt 1.",
        (
            "Community CLIPS validation rejected response attempt 1 with 1 blocking "
            "finding."
        ),
        (
            "Response attempt 1 rejected: 0 of 1 applied Reasoning Engines "
            "accepted it; Community CLIPS validation reported 1 blocking finding."
        ),
        (
            "Repair attempt 1 prepared for response attempt 2 from 1 blocking "
            "finding."
        ),
        "Requesting response attempt 2 using repair attempt 1.",
        "Extracting structured facts for response attempt 2.",
        "Structured facts extracted from response attempt 2.",
        "Evaluating Community CLIPS validation for response attempt 2.",
        (
            "Community CLIPS validation accepted response attempt 2 with no "
            "blocking findings."
        ),
        "Response attempt 2 accepted: 1 of 1 applied Reasoning Engines accepted it.",
        (
            "Analysis accepted response attempt 2 after 2 response attempts and "
            "1 repair attempt; it may proceed downstream."
        ),
    ]
    assert [item["sequence"] for item in events] == list(range(1, len(events) + 1))

    report = CSG.build_report("car-wash", "mock", None, "clips", 3)
    assert report["summary"] == events[-1]["message"]


def response_attempt(number, recommendation, target, clips, solver):
    return {
        "attempt": number,
        "answer": f"raw answer {number} must never appear in chronology",
        "facts": {
            "candidate_actions": [
                {
                    "id": f"action-{number}",
                    "recommendation": recommendation,
                    "target_location": target,
                }
            ]
        },
        "mechanisms": {
            "clips": {"status": clips},
            "solver": {"status": solver},
        },
    }


def test_response_chronology_uses_last_three_fact_summaries_oldest_to_newest() -> (
    None
):
    """Catches raw, unbounded, or reverse-ordered prior response context."""

    attempts = [
        response_attempt(1, "walk", "car_wash", "fail", "fail"),
        response_attempt(2, "drive", "car_wash", "fail", "pass"),
        response_attempt(3, "drive", "car_wash", "fail", "pass"),
        response_attempt(4, "drive", "car_wash", "pass", "pass"),
    ]

    chronology = CSG.build_response_chronology(attempts)
    assert chronology == (
        "Previous response chronology (oldest to newest; summaries, not verbatim):\n"
        "- Response attempt 2: recommended drive -> car_wash; accepted by Solver, "
        "rejected by CLIPS.\n"
        "- Response attempt 3: recommended drive -> car_wash; accepted by Solver, "
        "rejected by CLIPS.\n"
        "- Response attempt 4: recommended drive -> car_wash; accepted by CLIPS and Solver."
    )
    assert "raw answer" not in chronology


def test_repair_prompt_contains_original_question_chronology_and_latest_findings() -> (
    None
):
    """Catches a repair turn that omits the question or prior response outcome."""

    attempts = [response_attempt(1, "walk", "car_wash", "fail", "fail")]
    prompt = CSG.compose_repair_prompt(
        "Should I drive or walk to wash the car?",
        attempts,
        "Repair the car-location finding.",
    )

    assert "Original user question:" in prompt
    assert "Should I drive or walk to wash the car?" in prompt
    assert "Response attempt 1: recommended walk -> car_wash" in prompt
    assert "Repair the car-location finding." in prompt
    assert "raw answer 1" not in prompt


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (
            {
                "id": "select-single-best-eligible-discount",
                "discounts": ["welcome-25"],
            },
            "select-single-best-eligible-discount -> welcome-25",
        ),
        (
            {"id": "use-dock-door-b", "recommendation": "use_wider_approved_route"},
            "use_wider_approved_route",
        ),
        (
            {
                "id": "use-certified-cold-carrier",
                "carrier": "certified-cold-carrier",
            },
            "use-certified-cold-carrier -> certified-cold-carrier",
        ),
        ({}, "action unavailable"),
    ],
)
def test_response_attempt_summary_uses_bounded_fact_action_shapes(
    action, expected
) -> None:
    """Catches scenario-specific facts disappearing from the bounded summary."""

    attempt = {
        "attempt": 1,
        "facts": {"candidate_actions": [action]},
        "mechanisms": {},
    }

    assert f"recommended {expected};" in CSG.summarize_response_attempt(attempt)


def test_three_repairs_allow_four_responses_without_unused_packet() -> None:
    """Catches treating the repair budget as the total response budget."""

    scenario = CSG.load_scenario("car-wash")
    events = []
    provider_calls = []
    originals = {
        "make_provider": CSG.make_provider,
        "provider_chat": CSG.provider_chat,
        "facts_for_answer": CSG.facts_for_answer,
        "evaluate_mechanism": CSG.evaluate_mechanism,
        "fixture_llm_enabled": CSG.fixture_llm_enabled,
        "simulate_live_enabled": CSG.simulate_live_enabled,
    }

    def fake_provider_chat(provider, prompt, **_kwargs):
        provider_calls.append((provider, prompt))
        return f"Rejected response {len(provider_calls)}."

    def fake_evaluate(*_args, **_kwargs):
        return scenario["expected"]["expected_findings"], "live", "Rejected."

    try:
        CSG.make_provider = lambda phase=None: phase or "provider"
        CSG.provider_chat = fake_provider_chat
        CSG.facts_for_answer = lambda *_args, **_kwargs: (
            scenario["facts"],
            "live",
            "pass",
            "Facts extracted.",
        )
        CSG.evaluate_mechanism = fake_evaluate
        CSG.fixture_llm_enabled = lambda: False
        CSG.simulate_live_enabled = lambda: False

        loop = CSG.run_guardrail_loop(
            scenario,
            "live",
            ["clips"],
            max_repair_attempts=3,
            allow_fixture_fallback=False,
            auto_guardrails=False,
            event_sink=events.append,
            provider_id="ollama",
            model_id="test-model",
        )
    finally:
        for name, value in originals.items():
            setattr(CSG, name, value)

    assert len(provider_calls) == 4
    assert "Response attempt 1:" in provider_calls[1][1]
    assert "Response attempt 1:" in provider_calls[2][1]
    assert "Response attempt 2:" in provider_calls[2][1]
    assert "Response attempt 1:" in provider_calls[3][1]
    assert "Response attempt 2:" in provider_calls[3][1]
    assert "Response attempt 3:" in provider_calls[3][1]
    assert all(
        "Rejected response" not in prompt for _provider, prompt in provider_calls[1:]
    )
    assert len(loop["attempts"]) == 4
    assert [item["attempt"] for item in loop["attempts"]] == [1, 2, 3, 4]
    assert len(loop["repair_packets"]) == 3
    assert [item["attempt"] for item in loop["repair_packets"]] == [1, 2, 3]
    assert loop["final_status"] == "fail"
    retry_events = [item for item in events if item["status"] == "retry"]
    assert retry_events[-1]["attempt"] == 4
    assert all("attempt 5" not in item["message"].lower() for item in events)
    assert events[-1]["status"] == "rejected"
    assert events[-1]["message"] == (
        "Analysis rejected response attempt 4 after 4 response attempts and 3 "
        "repair attempts. Community CLIPS validation reported 1 blocking finding, "
        "so it is blocked from downstream use."
    )
    assert loop["terminal_summary"] == events[-1]["message"]


def test_live_events_do_not_add_provider_calls() -> None:
    scenario = CSG.load_scenario("car-wash")
    events = []
    provider_calls = []
    originals = {
        "make_provider": CSG.make_provider,
        "provider_chat": CSG.provider_chat,
        "facts_for_answer": CSG.facts_for_answer,
        "evaluate_mechanism": CSG.evaluate_mechanism,
        "fixture_llm_enabled": CSG.fixture_llm_enabled,
        "simulate_live_enabled": CSG.simulate_live_enabled,
    }

    def fake_provider_chat(provider, prompt, **_kwargs):
        provider_calls.append((provider, prompt))
        return "Walk to the wash." if provider == "baseline" else "Drive the car."

    def fake_evaluate(*_args, attempt, **_kwargs):
        findings = [] if attempt == 2 else scenario["expected"]["expected_findings"]
        return findings, "live", "Evaluated through nxusKit."

    try:
        CSG.make_provider = lambda phase=None: phase or "provider"
        CSG.provider_chat = fake_provider_chat
        CSG.facts_for_answer = lambda *_args, **_kwargs: (
            scenario["facts"],
            "live",
            "pass",
            "Facts extracted.",
        )
        CSG.evaluate_mechanism = fake_evaluate
        CSG.fixture_llm_enabled = lambda: False
        CSG.simulate_live_enabled = lambda: False

        CSG.run_guardrail_loop(
            scenario,
            "live",
            ["clips"],
            max_repair_attempts=3,
            allow_fixture_fallback=False,
            auto_guardrails=False,
            event_sink=events.append,
            provider_id="ollama",
            model_id="llama3:8b",
        )
    finally:
        for name, value in originals.items():
            setattr(CSG, name, value)

    assert [provider for provider, _prompt in provider_calls] == [
        "baseline",
        "repair",
    ]
    provider_events = [item for item in events if item["category"] == "provider"]
    assert [item["status"] for item in provider_events] == [
        "requested",
        "received",
        "requested",
        "received",
    ]
    assert all(item["component"]["id"] == "ollama" for item in provider_events)
    assert all(item["component"]["model"] == "llama3:8b" for item in provider_events)


class RecordingProvider:
    def __init__(self, content: str = "answer", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=self.content)


def interaction_context() -> LLMCallContext:
    return LLMCallContext(
        phase="initial_recommendation",
        response_attempt=1,
        source="live",
        provider="claude",
        model="claude-haiku-4-5",
    )


def test_provider_chat_records_one_existing_sdk_call() -> None:
    provider = RecordingProvider()
    interactions = []
    events = []
    recorder = LLMInteractionRecorder(sink=interactions.append)
    emitter = RunEventEmitter(sink=events.append)

    content = CSG.provider_chat(
        provider,
        "user prompt",
        system="system prompt",
        interaction_recorder=recorder,
        event_emitter=emitter,
        interaction_context=interaction_context(),
    )

    assert content == "answer"
    assert len(provider.calls) == 1
    assert [event["status"] for event in events] == ["requested", "received"]
    assert {event["llm_interaction_id"] for event in events} == {"llm-0001"}
    assert [item["status"] for item in interactions] == [
        "requested",
        "requested",
        "received",
        "received",
    ]
    assert interactions[-1]["linked_event_ids"] == ["event-0001", "event-0002"]
    assert interactions[-1]["response_content"] == "answer"


def test_provider_chat_names_cli_backend_in_linked_activity_events() -> None:
    """Catches a released-CLI Ollama call being mislabeled as generic Python SDK."""

    class CliBackendProvider(RecordingProvider):
        backend_label = "nxuskit-cli / Rust Ollama provider"

    provider = CliBackendProvider()
    events = []

    CSG.provider_chat(
        provider,
        "user prompt",
        system="system prompt",
        interaction_recorder=LLMInteractionRecorder(),
        event_emitter=RunEventEmitter(sink=events.append),
        interaction_context=LLMCallContext(
            phase="initial_recommendation",
            response_attempt=1,
            source="live",
            provider="ollama",
            model="gemma4:12b",
        ),
    )

    assert events[0]["message"] == (
        "Requesting the baseline recommendation through nxuskit-cli / Rust "
        "Ollama provider."
    )
    assert events[1]["message"] == (
        "The baseline recommendation was received through nxuskit-cli / Rust "
        "Ollama provider."
    )


def test_provider_chat_stops_safely_and_reraises_original_exception() -> None:
    error = RuntimeError("raw provider secret canary")
    provider = RecordingProvider(error=error)
    interactions = []
    events = []

    with pytest.raises(RuntimeError) as caught:
        CSG.provider_chat(
            provider,
            "user prompt",
            system="system prompt",
            interaction_recorder=LLMInteractionRecorder(sink=interactions.append),
            event_emitter=RunEventEmitter(sink=events.append),
            interaction_context=interaction_context(),
        )

    assert caught.value is error
    assert len(provider.calls) == 1
    assert [event["status"] for event in events] == ["requested", "stopped"]
    assert events[-1]["llm_interaction_id"] == "llm-0001"
    assert interactions[-1]["status"] == "stopped"
    assert interactions[-1]["safe_error"] == (
        "The provider request stopped before completion."
    )
    assert "raw provider secret canary" not in json.dumps(interactions + events)


def test_provider_chat_rejects_partial_instrumentation_before_sdk_call() -> None:
    provider = RecordingProvider()

    with pytest.raises(ValueError, match="all be supplied"):
        CSG.provider_chat(
            provider,
            "user prompt",
            system="system prompt",
            interaction_recorder=LLMInteractionRecorder(),
        )

    assert provider.calls == []


def test_make_provider_routes_explicit_ollama_through_released_cli(
    monkeypatch,
) -> None:
    """Catches a local Live run falling back to the defective v1.0.5 HTTP shape."""

    monkeypatch.setenv("NXUSKIT_PROVIDER", "ollama")
    monkeypatch.setenv("NXUSKIT_MODEL", "gemma4:12b")
    monkeypatch.setenv(
        "NXUSKIT_COMMON_SENSE_OLLAMA_READ_TIMEOUT_SECONDS",
        "345.5",
    )

    provider = CSG.make_provider("facts")

    assert isinstance(provider, NxuskitCliOllamaProvider)
    assert provider.model == "gemma4:12b"
    assert provider.timeout_seconds == 345.5
    assert provider.backend_label == "nxuskit-cli / Rust Ollama provider"


def test_ollama_timeout_defaults_to_five_minutes(monkeypatch) -> None:
    """Catches the old 120-second local-model deadline returning silently."""

    monkeypatch.delenv(
        "NXUSKIT_COMMON_SENSE_OLLAMA_READ_TIMEOUT_SECONDS",
        raising=False,
    )

    assert CSG.ollama_read_timeout_seconds() == 300.0


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "3600.1", "fast"])
def test_invalid_ollama_timeout_fails_before_provider_execution(
    monkeypatch, value: str
) -> None:
    """Catches unsafe or malformed local deadlines reaching subprocess execution."""

    monkeypatch.setenv(
        "NXUSKIT_COMMON_SENSE_OLLAMA_READ_TIMEOUT_SECONDS",
        value,
    )

    with pytest.raises(ValueError, match="finite number greater than 0 and at most 3600"):
        CSG.ollama_read_timeout_seconds()


def latest_interactions(snapshots: list[dict]) -> list[dict]:
    latest_by_id = {}
    for snapshot in snapshots:
        latest_by_id[snapshot["id"]] = snapshot
    return list(latest_by_id.values())


def test_fixture_repair_exposes_prompts_without_provider_contact() -> None:
    interactions = []

    record = CSG.build_reasoning_record(
        "car-wash",
        "mock",
        None,
        "clips",
        3,
        interaction_sink=interactions.append,
    )

    final = latest_interactions(interactions)
    assert [item["phase"] for item in final] == [
        "initial_recommendation",
        "fact_extraction",
        "repaired_recommendation",
        "fact_extraction",
    ]
    assert all(item["source"] == "fixture" for item in final)
    assert all(item["status"] == "received" for item in final)
    assert final[2]["repair_context"]["repair_attempt"] == 1
    assert final[2]["outcome"]["delta"] == "eliminated"
    assert record == CSG.build_reasoning_record("car-wash", "mock", None, "clips", 3)


class SequencedProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return SimpleNamespace(content=next(self.responses))


def run_live_interaction_record(
    *,
    baseline_responses: list[str],
    facts_responses: list[str],
    repair_responses: list[str],
    findings_by_attempt: dict[int, list[dict]],
    mode: str = "live",
) -> tuple[dict, list[dict], dict[str, SequencedProvider]]:
    providers = {
        "baseline": SequencedProvider(baseline_responses),
        "facts": SequencedProvider(facts_responses),
        "repair": SequencedProvider(repair_responses),
    }
    interactions = []
    originals = {
        "provider_env_present": CSG.provider_env_present,
        "make_provider": CSG.make_provider,
        "evaluate_mechanism": CSG.evaluate_mechanism,
        "fixture_llm_enabled": CSG.fixture_llm_enabled,
        "simulate_live_enabled": CSG.simulate_live_enabled,
    }

    def fake_evaluate(*_args, attempt, **_kwargs):
        findings = findings_by_attempt.get(attempt, [])
        return findings, "live", "Evaluated through nxusKit."

    try:
        CSG.provider_env_present = lambda: True
        CSG.make_provider = lambda phase=None: providers[phase]
        CSG.evaluate_mechanism = fake_evaluate
        CSG.fixture_llm_enabled = lambda: False
        CSG.simulate_live_enabled = lambda: False
        record = CSG.build_reasoning_record(
            "car-wash",
            mode,
            None,
            "clips",
            3,
            interaction_sink=interactions.append,
            provider_id="claude",
            model_id="claude-haiku-4-5",
        )
    finally:
        for name, value in originals.items():
            setattr(CSG, name, value)
    return record, latest_interactions(interactions), providers


def test_live_initial_acceptance_exposes_recommendation_and_facts_calls() -> None:
    scenario = CSG.load_scenario("car-wash")

    _record, interactions, providers = run_live_interaction_record(
        baseline_responses=["Drive the car to the car wash."],
        facts_responses=[json.dumps(scenario["corrected_facts"])],
        repair_responses=[],
        findings_by_attempt={1: []},
    )

    assert [item["phase"] for item in interactions] == [
        "initial_recommendation",
        "fact_extraction",
    ]
    assert all(item["source"] == "live" for item in interactions)
    assert interactions[0]["outcome"]["status"] == "accepted"
    assert len(providers["baseline"].calls) == 1
    assert len(providers["facts"].calls) == 1
    assert len(providers["repair"].calls) == 0


def test_live_repair_exposes_prompt_delta_and_measured_outcome() -> None:
    scenario = CSG.load_scenario("car-wash")

    _record, interactions, providers = run_live_interaction_record(
        baseline_responses=["Walk to the car wash."],
        facts_responses=[
            json.dumps(scenario["facts"]),
            json.dumps(scenario["corrected_facts"]),
        ],
        repair_responses=["Drive the car to the car wash."],
        findings_by_attempt={
            1: scenario["expected"]["expected_findings"],
            2: [],
        },
    )

    assert [item["phase"] for item in interactions] == [
        "initial_recommendation",
        "fact_extraction",
        "repaired_recommendation",
        "fact_extraction",
    ]
    repaired = interactions[2]
    assert repaired["repair_context"]["repair_attempt"] == 1
    assert repaired["repair_context"]["prompt_delta"]["added"]
    assert repaired["outcome"]["delta"] == "eliminated"
    assert [len(providers[name].calls) for name in ("baseline", "facts", "repair")] == [
        1,
        2,
        1,
    ]


def test_second_facts_call_is_classified_as_fact_extraction_repair() -> None:
    scenario = CSG.load_scenario("car-wash")

    _record, interactions, providers = run_live_interaction_record(
        baseline_responses=["Drive the car to the car wash."],
        facts_responses=[
            "not valid JSON",
            json.dumps(scenario["corrected_facts"]),
        ],
        repair_responses=[],
        findings_by_attempt={1: []},
    )

    assert [item["phase"] for item in interactions] == [
        "initial_recommendation",
        "fact_extraction",
        "fact_extraction_repair",
    ]
    assert len(providers["facts"].calls) == 2


def test_live_facts_prompt_is_compact_and_uses_scenario_specific_shape() -> None:
    scenario = CSG.load_scenario("cold-chain")
    provider = SequencedProvider([json.dumps(scenario["facts"])])

    CSG.facts_for_answer(
        scenario,
        "Use the cheap courier.",
        source="live",
        facts_provider=provider,
        allow_fixture_fallback=False,
    )

    prompt = provider.calls[0][0][1].content
    assert '"carrier":"<resources[].id>"' in prompt
    assert (
        "candidate_actions[0].carrier is a foreign key, not a display name" in prompt
    )
    assert "must exactly equal one resources[].id value" in prompt
    assert '"carrier_certified":false' in prompt
    assert '"temperature_logging":false' in prompt
    assert "Use at most 4 items per array" in prompt
    assert "Keep every string value under 120 characters" in prompt
    assert "cheap-courier" not in prompt
    assert "certified-cold-carrier" not in prompt
    assert provider.calls[0][1]["max_tokens"] == 900


def test_live_structured_validation_exhaustion_is_rejected_not_stopped() -> None:
    """Catches completed provider responses being mislabeled as interrupted calls."""

    scenario = CSG.load_scenario("cold-chain")
    events = []
    originals = {
        "make_provider": CSG.make_provider,
        "provider_chat": CSG.provider_chat,
        "facts_for_answer": CSG.facts_for_answer,
        "fixture_llm_enabled": CSG.fixture_llm_enabled,
        "simulate_live_enabled": CSG.simulate_live_enabled,
    }

    def invalid_facts(*_args, **_kwargs):
        raise CSG.StructuredJsonError("carrier foreign key mismatch")

    try:
        CSG.make_provider = lambda phase=None: phase or "provider"
        CSG.provider_chat = lambda *_args, **_kwargs: (
            "Use a certified refrigerated carrier with temperature logging."
        )
        CSG.facts_for_answer = invalid_facts
        CSG.fixture_llm_enabled = lambda: False
        CSG.simulate_live_enabled = lambda: False

        with pytest.raises(CSG.StructuredJsonError, match="carrier foreign key"):
            CSG.run_guardrail_loop(
                scenario,
                "live",
                ["clips", "bn", "zen"],
                max_repair_attempts=3,
                allow_fixture_fallback=False,
                auto_guardrails=False,
                event_sink=events.append,
                provider_id="ollama",
                model_id="gemma4:12b",
            )
    finally:
        for name, value in originals.items():
            setattr(CSG, name, value)

    assert events[-1]["category"] == "facts"
    assert events[-1]["status"] == "rejected"
    assert events[-1]["message"] == (
        "Structured fact responses were received but could not be validated for "
        "response attempt 1."
    )


def test_live_facts_repair_rejects_generic_shape_missing_scenario_fields() -> None:
    scenario = CSG.load_scenario("cold-chain")
    generic = {
        "goal": "ship samples",
        "candidate_actions": [{"id": "ship", "recommendation": "use carrier"}],
        "objects_required": [],
        "objects_moved": [],
        "resources": [{"id": "carrier", "type": "carrier", "state": "ready"}],
        "constraints": [],
        "policy_context": {"domain": "physical_planning"},
        "confidence": 0.8,
    }
    provider = SequencedProvider(
        [json.dumps(generic), json.dumps(scenario["corrected_facts"])]
    )

    facts, source, status, _message = CSG.facts_for_answer(
        scenario,
        "Use a certified refrigerated carrier with temperature logging.",
        source="live",
        facts_provider=provider,
        allow_fixture_fallback=False,
    )

    assert facts == scenario["corrected_facts"]
    assert source == "live"
    assert status == "pass"
    assert len(provider.calls) == 2
    repaired_prompt = provider.calls[1][0][1].content
    assert "Validation feedback:" in repaired_prompt
    assert "candidate_actions items missing key 'carrier'" in repaired_prompt


def test_live_facts_repair_rejects_rejected_cold_chain_carrier_projection() -> None:
    scenario = CSG.load_scenario("cold-chain")
    provider = SequencedProvider(
        [
            json.dumps(scenario["facts"]),
            json.dumps(scenario["corrected_facts"]),
        ]
    )

    facts, source, status, _message = CSG.facts_for_answer(
        scenario,
        scenario["problem"]["expected_corrected_answer"],
        source="live",
        facts_provider=provider,
        allow_fixture_fallback=False,
    )

    assert facts == scenario["corrected_facts"]
    assert source == "live"
    assert status == "pass"
    assert len(provider.calls) == 2
    initial_prompt = provider.calls[0][0][1].content
    assert "primary recommended action first" in initial_prompt
    assert "omit explicitly rejected alternatives" in initial_prompt
    repair_prompt = provider.calls[1][0][1].content
    assert "selected carrier must not be the rejected cheap courier" in repair_prompt


def test_auto_retains_stopped_live_interaction_before_fixture_fallback() -> None:
    error = RuntimeError("provider unavailable")
    interactions = []
    originals = {
        "provider_env_present": CSG.provider_env_present,
        "make_provider": CSG.make_provider,
        "fixture_llm_enabled": CSG.fixture_llm_enabled,
        "simulate_live_enabled": CSG.simulate_live_enabled,
    }
    try:
        CSG.provider_env_present = lambda: True
        CSG.make_provider = lambda _phase=None: RecordingProvider(error=error)
        CSG.fixture_llm_enabled = lambda: False
        CSG.simulate_live_enabled = lambda: False
        CSG.build_reasoning_record(
            "car-wash",
            "auto",
            None,
            "clips",
            3,
            interaction_sink=interactions.append,
            provider_id="claude",
            model_id="claude-haiku-4-5",
        )
    finally:
        for name, value in originals.items():
            setattr(CSG, name, value)

    final = latest_interactions(interactions)
    assert final[0]["status"] == "stopped"
    assert final[0]["source"] == "live"
    assert any(item["source"] == "fixture" for item in final[1:])


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
        if scenario == "coupon-stack":
            assert proc.returncode == 2
            assert proc.stdout == ""
            assert "coupon_live_strict_schema_transport_unavailable_v1_0_5" in (
                proc.stderr
            )
            continue
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
  if jq -e '((.input.discount_count // 0) > 0 and (.input.discount_count // 99) <= 1 and (.input.combined_margin_percent // -99) >= 0) or ((.input.discount_count // -1) == 0 and .input.carrier_certified == true and .input.handoff_record == true and .input.refrigerated == true and .input.temperature_logging == true)' "$input" >/dev/null; then
    printf '{"result":{"output":{"allowed":true,"decision":"allow_single_discount"}}}\\n' > "$output"
  else
    printf '{"result":{"output":{"allowed":false,"decision":"deny_stack","repair_hint":"choose one eligible promotion"}}}\\n' > "$output"
  fi
elif [[ "$cmd $sub" == "bn infer" ]]; then
  if jq -e '(.evidence.discount_count_bucket == "low" and .evidence.margin_floor_breach == "no" and .evidence.non_stackable_conflict == "no") or (.evidence.carrier_certified == "yes" and .evidence.handoff_record == "yes" and .evidence.refrigerated == "yes" and .evidence.temperature_logging == "yes")' "$input" >/dev/null; then
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
            "cold-chain",
            "--mode",
            "live",
            "--stage",
            "pro",
            "--json",
            env=env,
        )
        bn_proc = run_py(
            "--scenario",
            "cold-chain",
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


def test_coupon_auto_resolves_to_mock_before_provider_preflight() -> None:
    calls = []
    original = CSG.provider_env_present
    try:
        CSG.provider_env_present = lambda: calls.append("preflight") or True
        resolution = CSG.resolve_mode("auto", scenario_id="coupon-stack")
    finally:
        CSG.provider_env_present = original
    assert calls == []
    assert resolution["source"] == "mock"
    assert resolution["provider_contacted"] is False
    assert resolution["compatibility_code"] == (
        "coupon_live_strict_schema_transport_unavailable_v1_0_5"
    )


def test_coupon_live_rejected_before_provider_preflight() -> None:
    calls = []
    original = CSG.provider_env_present
    try:
        CSG.provider_env_present = lambda: calls.append("preflight") or True
        with pytest.raises(RuntimeError, match="^coupon_live_strict_schema"):
            CSG.resolve_mode("live", scenario_id="coupon-stack")
    finally:
        CSG.provider_env_present = original
    assert calls == []


def test_coupon_fixture_remains_available() -> None:
    resolution = CSG.resolve_mode("mock", scenario_id="coupon-stack")
    assert resolution == {
        "requested": "mock",
        "source": "mock",
        "provider_available": False,
        "message": (
            "mock mode uses checked-in fixtures and performs no provider preflight"
        ),
    }


def _coupon_contact_canary_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    sentinel = tmp_path / "provider-contacted"
    fake_cli = tmp_path / "nxuskit-cli"
    fake_cli.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "provider command reached\\n" >> "$NXUSKIT_COUPON_CONTACT_SENTINEL"\n'
        "exit 97\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)
    env = clean_env()
    env.update(
        {
            "NXUSKIT_CLI": str(fake_cli),
            "NXUSKIT_COUPON_CONTACT_SENTINEL": str(sentinel),
            "NXUSKIT_PROVIDER": "literal-coupon-provider-canary",
            "NXUSKIT_MODEL": "literal-coupon-model-canary",
        }
    )
    return env, sentinel


def test_coupon_auto_cli_contains_before_provider_contact(tmp_path: Path) -> None:
    env, sentinel = _coupon_contact_canary_env(tmp_path)
    proc = run_py(
        "--scenario",
        "coupon-stack",
        "--mode",
        "auto",
        "--guardrails",
        "clips,bn",
        "--json",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert not sentinel.exists()
    report = json.loads(proc.stdout)
    assert report["mode"] == "auto"
    assert report["resolved_mode"] == "mock"
    assert report["mode_resolution"]["provider_contacted"] is False
    assert report["mode_resolution"]["compatibility_code"] == (
        "coupon_live_strict_schema_transport_unavailable_v1_0_5"
    )
    assert all(stage["source"] == "mock" for stage in report["stages"])


def test_coupon_live_cli_rejects_before_provider_contact(tmp_path: Path) -> None:
    env, sentinel = _coupon_contact_canary_env(tmp_path)
    proc = run_py(
        "--scenario",
        "coupon-stack",
        "--mode",
        "live",
        "--guardrails",
        "clips,bn",
        "--json",
        env=env,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.strip() == (
        "ERROR: coupon_live_strict_schema_transport_unavailable_v1_0_5: "
        "coupon-stack live mode is unavailable with nxusKit v1.0.5 because the "
        "Python provider path cannot preserve the required strict schema; use "
        "--mode auto or --mode mock"
    )
    assert not sentinel.exists()


@pytest.mark.parametrize("scenario", ["car-wash", "pallet-door", "cold-chain"])
def test_non_coupon_mode_resolution_remains_unchanged(scenario: str) -> None:
    calls = []
    original = CSG.provider_env_present
    try:
        CSG.provider_env_present = lambda: calls.append("preflight") or False
        resolution = CSG.resolve_mode("auto", scenario_id=scenario)
    finally:
        CSG.provider_env_present = original
    assert calls == ["preflight"]
    assert resolution == {
        "requested": "auto",
        "source": "mock",
        "provider_available": False,
        "message": "auto mode did not find a live provider; using checked-in fixtures",
    }


def test_coupon_auto_python_output_validates_public_run_schema() -> None:
    report = CSG.build_report("coupon-stack", "auto", "ce", "clips")
    assert report["mode_resolution"]["provider_contacted"] is False
    assert report["mode_resolution"]["compatibility_code"] == (
        "coupon_live_strict_schema_transport_unavailable_v1_0_5"
    )
    validate_run_output(report)


def test_coupon_auto_bash_output_validates_public_run_schema() -> None:
    report = run_bash_json(
        "--scenario",
        "coupon-stack",
        "--mode",
        "auto",
        "--guardrails",
        "clips",
    )
    assert report["mode_resolution"]["provider_contacted"] is False
    assert report["mode_resolution"]["compatibility_code"] == (
        "coupon_live_strict_schema_transport_unavailable_v1_0_5"
    )
    validate_run_output(report)


@pytest.mark.parametrize("scenario", ["car-wash", "pallet-door", "cold-chain"])
def test_non_coupon_python_output_validates_public_run_schema(scenario: str) -> None:
    report = CSG.build_report(scenario, "mock", "ce", "clips")
    assert "provider_contacted" not in report["mode_resolution"]
    assert "compatibility_code" not in report["mode_resolution"]
    validate_run_output(report)


@pytest.mark.parametrize("scenario", ["car-wash", "pallet-door", "cold-chain"])
def test_non_coupon_bash_output_validates_public_run_schema(scenario: str) -> None:
    report = run_bash_json(
        "--scenario", scenario, "--mode", "mock", "--guardrails", "clips"
    )
    assert "provider_contacted" not in report["mode_resolution"]
    assert "compatibility_code" not in report["mode_resolution"]
    validate_run_output(report)


@pytest.mark.parametrize("producer", ["python", "bash"])
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("provider_contacted", None),
        ("provider_contacted", True),
        ("compatibility_code", None),
        ("compatibility_code", "wrong-code"),
    ],
)
def test_coupon_auto_public_run_schema_rejects_invalid_receipt(
    producer: str,
    field: str,
    replacement: object,
) -> None:
    report = (
        CSG.build_report("coupon-stack", "auto", "ce", "clips")
        if producer == "python"
        else run_bash_json(
            "--scenario",
            "coupon-stack",
            "--mode",
            "auto",
            "--guardrails",
            "clips",
        )
    )
    mutated = json.loads(json.dumps(report))
    if replacement is None:
        del mutated["mode_resolution"][field]
    else:
        mutated["mode_resolution"][field] = replacement
    with pytest.raises(jsonschema.ValidationError):
        validate_run_output(mutated)


def test_live_without_provider_fails_clearly() -> None:
    proc = run_py("--scenario", "car-wash", "--mode", "live", "--stage", "ce")
    assert proc.returncode != 0
    assert "live mode requires" in proc.stderr


def test_default_mode_is_live_and_fails_without_provider() -> None:
    proc = run_py("--scenario", "car-wash", "--stage", "ce")
    assert proc.returncode != 0
    assert "live mode requires" in proc.stderr


def test_local_provider_readiness_delegates_to_released_nxuskit_cli() -> None:
    """Catches direct provider probing outside the released nxusKit boundary."""

    calls: list[str] = []
    original_env = os.environ.copy()
    original_reachable = getattr(CSG, "provider_reachable", None)
    try:
        os.environ.clear()
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
        CSG.provider_reachable = lambda provider: calls.append(provider) or True
        assert CSG.provider_env_present() is True
    finally:
        os.environ.clear()
        os.environ.update(original_env)
        if original_reachable is None:
            delattr(CSG, "provider_reachable")
        else:
            CSG.provider_reachable = original_reachable

    assert calls == ["ollama"]


def test_provider_discovery_imports_no_raw_http_or_socket_clients() -> None:
    """Catches reintroduction of a provider access path outside nxusKit."""

    tree = ast.parse((PY_DIR / "main.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "socket" not in imported
    assert "urllib.error" not in imported
    assert "urllib.request" not in imported


def test_ollama_provider_uses_selected_model_and_local_timeout() -> None:
    original_env = os.environ.copy()
    try:
        os.environ["NXUSKIT_PROVIDER"] = "ollama"
        os.environ["NXUSKIT_MODEL"] = "llama3.1:8b"
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
        os.environ["NXUSKIT_COMMON_SENSE_OLLAMA_READ_TIMEOUT_SECONDS"] = "300"
        provider = CSG.make_provider()
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    assert isinstance(provider, NxuskitCliOllamaProvider)
    assert provider.model == "llama3.1:8b"
    assert provider.timeout_seconds == 300.0


def test_groq_and_xai_use_the_released_v105_provider_constructors() -> None:
    """Catches advertised live-provider choices falling through to Ollama."""

    calls: list[tuple[str, dict]] = []

    class FakeProvider:
        @staticmethod
        def groq(**kwargs):
            calls.append(("groq", kwargs))
            return object()

        @staticmethod
        def xai(**kwargs):
            calls.append(("xai", kwargs))
            return object()

        @staticmethod
        def lmstudio(**kwargs):
            calls.append(("lmstudio", kwargs))
            return object()

    original_module = sys.modules.get("nxuskit")
    fake_module = type(sys)("nxuskit")
    fake_module.Provider = FakeProvider
    sys.modules["nxuskit"] = fake_module
    original_env = os.environ.copy()
    try:
        os.environ["NXUSKIT_PROVIDER"] = "groq"
        os.environ["NXUSKIT_MODEL"] = "groq-test-model"
        os.environ["GROQ_API_KEY"] = "canary-groq-key"
        assert CSG.provider_env_present() is True
        CSG.make_provider()
        os.environ["NXUSKIT_PROVIDER"] = "xai"
        os.environ["NXUSKIT_MODEL"] = "xai-test-model"
        os.environ["XAI_API_KEY"] = "canary-xai-key"
        assert CSG.provider_env_present() is True
        CSG.make_provider()
        os.environ["NXUSKIT_PROVIDER"] = "lmstudio"
        os.environ["NXUSKIT_MODEL"] = "local-test-model"
        os.environ["LMSTUDIO_BASE_URL"] = "http://127.0.0.1:1234"
        CSG.make_provider()
    finally:
        os.environ.clear()
        os.environ.update(original_env)
        if original_module is None:
            sys.modules.pop("nxuskit", None)
        else:
            sys.modules["nxuskit"] = original_module

    assert [name for name, _kwargs in calls] == ["groq", "xai", "lmstudio"]
    assert calls[0][1]["model"] == "groq-test-model"
    assert calls[1][1]["model"] == "xai-test-model"
    assert calls[2][1]["model"] == "local-test-model"


def test_phase_specific_ollama_model_overrides_global_model() -> None:
    original_env = os.environ.copy()
    try:
        os.environ["NXUSKIT_PROVIDER"] = "ollama"
        os.environ["NXUSKIT_MODEL"] = "llama3.2"
        os.environ["NXUSKIT_COMMON_SENSE_FACTS_MODEL"] = "qwen3:4b"
        os.environ["OLLAMA_HOST"] = "http://127.0.0.1:11434"
        providers = [
            CSG.make_provider("baseline"),
            CSG.make_provider("facts"),
            CSG.make_provider("repair"),
        ]
    finally:
        os.environ.clear()
        os.environ.update(original_env)

    assert all(isinstance(provider, NxuskitCliOllamaProvider) for provider in providers)
    assert [provider.model for provider in providers] == [
        "llama3.2",
        "qwen3:4b",
        "llama3.2",
    ]


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


def test_live_mode_fails_closed_when_structured_fact_json_invalid() -> None:
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
        try:
            CSG.live_ce_stages(scenario, allow_fixture_fallback=False)
        except CSG.StructuredJsonError:
            pass
        else:
            raise AssertionError("expected Live structured extraction to fail closed")
    finally:
        CSG.make_provider = original_make_provider
        CSG.provider_chat = original_provider_chat
        CSG.live_clips_findings = original_live_clips_findings


def test_car_wash_clips_rejects_walking_but_accepts_moving_the_car() -> None:
    """Catches the walking-only rule rejecting live facts that move the car."""

    scenario = CSG.load_scenario("car-wash")
    driving_facts = json.loads(json.dumps(scenario["corrected_facts"]))
    driving_facts["objects_required"][0].update(
        {
            "current_location": "home",
            "present_at_required_location": False,
        }
    )

    walking = CSG.live_clips_findings(scenario, scenario["facts"])["findings"]
    driving = CSG.live_clips_findings(scenario, driving_facts)["findings"]

    assert [item["rule_id"] for item in walking] == ["car-required-at-wash"]
    assert not any(item["status"] == "fail" for item in driving)


def test_car_wash_engines_bind_movement_to_selected_action_and_destination() -> None:
    scenario = CSG.load_scenario("car-wash")
    facts = json.loads(json.dumps(scenario["corrected_facts"]))
    facts["objects_required"].insert(
        0,
        {
            "object": "person",
            "required_location": "car_wash",
            "current_location": "home",
            "present_at_required_location": False,
        },
    )
    facts["candidate_actions"] = [
        {
            "id": "walk-to-car-wash",
            "moves": ["person"],
            "recommendation": "walk",
            "target_location": "car_wash",
        },
        *facts["candidate_actions"],
    ]
    facts["objects_moved"] = [
        {
            "action_id": "walk-to-car-wash",
            "object": "person",
            "from": "home",
            "to": "car_wash",
        },
        {
            "action_id": "drive-car-to-wash",
            "object": "car",
            "from": "home",
            "to": "car_wash",
        },
    ]
    facts["objects_required"][1].update(
        {
            "current_location": "home",
            "present_at_required_location": False,
        }
    )

    clips = CSG.live_clips_findings(scenario, facts)["findings"]
    solver = CSG.solver_input_from_facts(scenario, facts)

    assert [item["rule_id"] for item in clips] == ["car-required-at-wash"]
    presence = next(
        item for item in solver["variables"]
        if item["name"] == "required_object_present_after_action"
    )
    assert presence["domain"] == {"min": 0, "max": 0}


def test_car_wash_engines_reject_selected_action_moving_car_elsewhere() -> None:
    scenario = CSG.load_scenario("car-wash")
    facts = json.loads(json.dumps(scenario["corrected_facts"]))
    facts["objects_required"][0].update(
        {
            "current_location": "home",
            "present_at_required_location": False,
        }
    )
    for movement in facts["objects_moved"]:
        if movement["object"] == "car":
            movement["to"] = "parking_lot"

    clips = CSG.live_clips_findings(scenario, facts)["findings"]
    solver = CSG.solver_input_from_facts(scenario, facts)

    assert [item["rule_id"] for item in clips] == ["car-required-at-wash"]
    presence = next(
        item for item in solver["variables"]
        if item["name"] == "required_object_present_after_action"
    )
    assert presence["domain"] == {"min": 0, "max": 0}


def test_car_wash_engines_reject_contradictory_presence_without_movement() -> None:
    scenario = CSG.load_scenario("car-wash")
    facts = json.loads(json.dumps(scenario["facts"]))
    facts["objects_required"][0]["present_at_required_location"] = True

    clips = CSG.live_clips_findings(scenario, facts)["findings"]
    solver = CSG.solver_input_from_facts(scenario, facts)

    assert [item["rule_id"] for item in clips] == ["car-required-at-wash"]
    presence = next(
        item for item in solver["variables"]
        if item["name"] == "required_object_present_after_action"
    )
    assert presence["domain"] == {"min": 0, "max": 0}


def test_pallet_solver_uses_selected_route_evidence_not_recommendation_words() -> None:
    scenario = CSG.load_scenario("pallet-door")
    facts = json.loads(json.dumps(scenario["facts"]))
    facts["candidate_actions"][0]["recommendation"] = "use an approved alternate approach"
    solver = CSG.solver_input_from_facts(scenario, facts)
    route = next(
        item for item in solver["variables"] if item["name"] == "route_width_inches"
    )
    assert route["domain"] == {"min": 42, "max": 42}


def test_pallet_clips_rejects_unsafe_loaded_tilt_without_fixture_specific_id() -> None:
    scenario = CSG.load_scenario("pallet-door")
    facts = json.loads(json.dumps(scenario["corrected_facts"]))
    facts["candidate_actions"][0].update(
        {
            "id": "tilt-and-force-through-wide-opening",
            "recommendation": "tilt the loaded pallet and force it through",
        }
    )
    findings = CSG.live_clips_findings(scenario, facts)["findings"]
    assert "tilt-unsafe-for-load" in {item["rule_id"] for item in findings}


def test_coupon_engines_reject_policy_breach_without_fixture_specific_ids() -> None:
    scenario = CSG.load_scenario("coupon-stack")
    facts = json.loads(json.dumps(scenario["facts"]))
    facts["candidate_actions"][0].update(
        {
            "id": "apply-available-discounts",
            "discounts": ["employee-15", "welcome-25"],
        }
    )
    facts["policy_context"].update(
        {"margin_percent_after_stack": 10, "non_stackable_count": 1}
    )

    clips = CSG.live_clips_findings(scenario, facts)["findings"]
    evidence = CSG.bn_evidence_from_facts(scenario, facts)
    zen = CSG.live_zen_findings(scenario, facts)

    assert {item["rule_id"] for item in clips} == {
        "non-stackable-discount-conflict",
        "margin-floor-breach",
    }
    assert evidence["non_stackable_conflict"] == "yes"
    assert zen[0]["status"] == "fail"


def test_cold_chain_clips_rejects_each_missing_required_condition() -> None:
    scenario = CSG.load_scenario("cold-chain")
    cases = {
        "carrier_certified": "carrier-not-certified",
        "refrigerated": "carrier-not-refrigerated",
        "temperature_logging": "temperature-logging-missing",
        "action_temperature_logging": "temperature-logging-missing",
        "handoff_record": "custody-handoff-missing",
        "temperature_monitoring": "temperature-audit-missing",
    }
    for field, expected_rule in cases.items():
        facts = json.loads(json.dumps(scenario["corrected_facts"]))
        if field in {"refrigerated", "temperature_logging"}:
            facts["resources"][0][field] = False
        elif field == "action_temperature_logging":
            facts["candidate_actions"][0]["temperature_logging"] = False
        else:
            facts["policy_context"][field] = False
        findings = CSG.live_clips_findings(scenario, facts)["findings"]
        assert expected_rule in {item["rule_id"] for item in findings}, field


def test_cold_chain_bn_and_zen_reject_each_missing_required_condition() -> None:
    scenario = CSG.load_scenario("cold-chain")
    fields = (
        "carrier_certified",
        "refrigerated",
        "temperature_logging",
        "action_temperature_logging",
        "handoff_record",
        "temperature_monitoring",
    )
    for field in fields:
        facts = json.loads(json.dumps(scenario["corrected_facts"]))
        if field in {"refrigerated", "temperature_logging"}:
            facts["resources"][0][field] = False
        elif field == "action_temperature_logging":
            facts["candidate_actions"][0]["temperature_logging"] = False
        else:
            facts["policy_context"][field] = False
        assert CSG.live_bn_findings(scenario, facts)[0]["status"] == "fail", field
        assert CSG.live_zen_findings(scenario, facts)[0]["status"] == "fail", field


@pytest.mark.parametrize(
    ("scenario_id", "mechanism"),
    (
        ("car-wash", "clips"),
        ("car-wash", "solver"),
        ("pallet-door", "clips"),
        ("pallet-door", "solver"),
        ("coupon-stack", "clips"),
        ("coupon-stack", "bn"),
        ("coupon-stack", "zen"),
        ("cold-chain", "clips"),
        ("cold-chain", "bn"),
        ("cold-chain", "zen"),
    ),
)
def test_real_engine_matrix_rejects_baseline_and_accepts_correction(
    scenario_id: str, mechanism: str
) -> None:
    scenario = CSG.load_scenario(scenario_id)

    def status(facts: dict) -> str:
        if mechanism == "clips":
            findings = CSG.live_clips_findings(scenario, facts)["findings"]
        elif mechanism == "solver":
            findings = CSG.live_solver_findings(scenario, facts)
        elif mechanism == "bn":
            findings = CSG.live_bn_findings(scenario, facts)
        else:
            findings = CSG.live_zen_findings(scenario, facts)
        return "fail" if any(item["status"] == "fail" for item in findings) else "pass"

    assert status(scenario["facts"]) == "fail"
    assert status(scenario["corrected_facts"]) == "pass"


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


def test_live_structured_facts_uses_bounded_900_token_budget() -> None:
    captured: list[int] = []
    complete = json.dumps(
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

    original_provider_chat = CSG.provider_chat
    try:
        CSG.provider_chat = lambda *_args, **kwargs: (
            captured.append(kwargs["max_tokens"])
            or complete
            if kwargs["max_tokens"] >= CSG.STRUCTURED_FACTS_MAX_TOKENS
            else '{"goal":{"object":"car"},"candidate_actions":['
        )
        facts, status, _message = CSG.live_structured_facts(object(), "extract")
    finally:
        CSG.provider_chat = original_provider_chat

    assert facts["goal"] == "wash car"
    assert status == "pass"
    assert captured == [CSG.STRUCTURED_FACTS_MAX_TOKENS]
    assert CSG.STRUCTURED_FACTS_MAX_TOKENS == 900


def test_live_structured_facts_sends_json_schema_to_cli_adapter() -> None:
    """Catches the v1.0.5 compatibility path degrading schema output to plain JSON."""

    captured: list[object] = []
    complete = json.dumps(
        {
            "goal": {"object": "car"},
            "candidate_actions": [],
            "objects_required": [],
            "objects_moved": [],
            "resources": [],
            "constraints": [],
            "policy_context": {},
            "confidence": 0.9,
        }
    )
    provider = NxuskitCliOllamaProvider(
        model="gemma4:12b",
        timeout_seconds=300,
        cli_path=Path("/opt/nxuskit/bin/nxuskit-cli"),
    )
    original_provider_chat = CSG.provider_chat
    try:
        CSG.provider_chat = lambda *_args, **kwargs: (
            captured.append(kwargs.get("response_format")) or complete
        )
        facts, status, _message = CSG.live_structured_facts(provider, "extract")
    finally:
        CSG.provider_chat = original_provider_chat

    assert facts["goal"] == {"object": "car"}
    assert status == "pass"
    assert len(captured) == 1
    response_format = captured[0]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"
    schema = response_format["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "goal",
        "candidate_actions",
        "objects_required",
        "objects_moved",
        "resources",
        "constraints",
        "policy_context",
        "confidence",
    ]


def test_structured_json_rejects_nested_fragment_from_truncated_outer_object() -> None:
    truncated = (
        '{"goal":{"object":"car","outcome":"washed",'
        '"target_location":"car-wash"},"candidate_actions":['
    )

    try:
        CSG.parse_facts_response(truncated)
    except CSG.StructuredJsonError as exc:
        assert "complete facts JSON object" in str(exc)
    else:
        raise AssertionError("expected StructuredJsonError")


def test_structured_json_rejects_complete_facts_nested_in_truncated_wrapper() -> None:
    nested_facts = json.dumps(
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
    truncated = f'{{"wrapper":{nested_facts},"tail":'

    try:
        CSG.parse_facts_response(truncated)
    except CSG.StructuredJsonError as exc:
        assert "complete facts JSON object" in str(exc)
    else:
        raise AssertionError("expected StructuredJsonError")


def test_structured_json_rejects_fenced_facts_nested_in_truncated_wrapper() -> None:
    nested_facts = json.dumps(
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
    truncated = f'{{"wrapper":```json\n{nested_facts}\n``` ,"tail":'

    try:
        CSG.parse_facts_response(truncated)
    except CSG.StructuredJsonError as exc:
        assert "complete facts JSON object" in str(exc)
    else:
        raise AssertionError("expected StructuredJsonError")


def test_structured_json_rejects_complete_facts_nested_in_array() -> None:
    nested_facts = json.dumps(
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

    for wrapped in (f"[{nested_facts}]", f"[{nested_facts}"):
        try:
            CSG.parse_facts_response(wrapped)
        except CSG.StructuredJsonError as exc:
            assert "facts JSON object" in str(exc) or "must be an object" in str(exc)
        else:
            raise AssertionError("expected StructuredJsonError")


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
    assert len(ex["scenarios"]) == 5
    assert any(
        scenario["name"] == "synthetic-claims-audit"
        and scenario["cli"]
        == "python marimo/frontend_core.py --analyze --scenario synthetic-claims-audit"
        for scenario in ex["scenarios"]
    )
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
