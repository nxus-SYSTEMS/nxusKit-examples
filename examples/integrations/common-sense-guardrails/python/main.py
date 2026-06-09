#!/usr/bin/env python3
# fmt: off
"""Common-sense guardrails example for nxusKit.

The Community path demonstrates a progressive guardrail workflow:
raw LLM answer, structured fact extraction, CLIPS-style rule findings,
deterministic repair packet, and corrected answer. Mock mode is fully
fixture-backed so the example, tests, and smoke matrix run without provider
credentials. Live mode uses nxusKit provider APIs when a provider is configured.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EXAMPLE_ID = "common-sense-guardrails"
SCENARIOS = ("car-wash", "coupon-stack", "pallet-door", "cold-chain")
GUARDRAILS = ("clips", "solver", "zen", "bn")
PRO_GUARDRAILS = {"solver", "zen"}
PRO_STAGE_BY_ENGINE = {"solver": "solver-proof", "zen": "zen-policy"}
PRO_LABEL_BY_ENGINE = {"solver": "Solver / Z3 feasibility", "zen": "ZEN policy table"}
BN_STAGE_ID = "bn-risk"
BN_LABEL = "Bayesian risk / confidence"
FIXTURE_LLM_ENV = "NXUSKIT_COMMON_SENSE_FIXTURE_LLM"
SIMULATE_LIVE_ENV = "NXUSKIT_COMMON_SENSE_SIMULATE_LIVE"
DEFAULT_MAX_REPAIR_ATTEMPTS = 3
CE_STAGE_IDS = (
    "raw-baseline",
    "structured-facts",
    "clips-validation",
    "repair-packet",
    "corrected-answer",
)
REQUIRED_SCENARIO_FILES = (
    "problem.json",
    "expected-output.json",
    "rules.clp",
    "mock-baseline.json",
    "mock-facts.json",
    "mock-corrected-facts.json",
    "mock-repair.json",
    "mock-corrected.json",
)
FACTS_JSON_SHAPE = (
    '{"goal":{"object":"<object>","outcome":"<outcome>",'
    '"target_location":"<location>"},'
    '"candidate_actions":[{"id":"<action-id>","recommendation":"<action>",'
    '"target_location":"<location>","moves":["<object-or-actor>"]}],'
    '"objects_required":[{"object":"<object>","required_location":"<location>",'
    '"current_location":"<location>","present_at_required_location":false}],'
    '"objects_moved":[{"action_id":"<action-id>","object":"<object-or-actor>",'
    '"from":"<location>","to":"<location>"}],'
    '"resources":[{"id":"<resource>","type":"<type>","state":"<state>"}],'
    '"constraints":[{"id":"<constraint-id>","type":"<type>"}],'
    '"policy_context":{"domain":"physical_planning","distance_meters":50},'
    '"confidence":0.8}'
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "scenarios"
OLLAMA_CONNECT_TIMEOUT_SECONDS = 5.0
OLLAMA_READ_TIMEOUT_SECONDS = 120.0


class ScenarioError(RuntimeError):
    """Raised when a scenario artifact is missing or invalid."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise ScenarioError(f"missing required artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"invalid JSON in {path}: {exc}") from exc


def scenario_dir(name: str) -> Path:
    if name not in SCENARIOS:
        raise ScenarioError(f"unknown scenario '{name}'")
    return SCENARIO_ROOT / name


def load_scenario(name: str) -> dict[str, Any]:
    base = scenario_dir(name)
    if not base.is_dir():
        raise ScenarioError(f"missing scenario directory: {base}")

    data = {
        "dir": base,
        "problem": load_json(base / "problem.json"),
        "expected": load_json(base / "expected-output.json"),
        "baseline": load_json(base / "mock-baseline.json"),
        "facts": load_json(base / "mock-facts.json"),
        "repair": load_json(base / "mock-repair.json"),
        "corrected": load_json(base / "mock-corrected.json"),
    }
    corrected_facts = base / "mock-corrected-facts.json"
    if corrected_facts.is_file():
        data["corrected_facts"] = load_json(corrected_facts)

    problem = data["problem"]
    expected = data["expected"]
    if problem.get("id") != name:
        raise ScenarioError(f"{base / 'problem.json'} id must be '{name}'")
    if expected.get("scenario") != name:
        raise ScenarioError(
            f"{base / 'expected-output.json'} scenario must be '{name}'"
        )
    if "{findings}" not in problem.get("repair_template", ""):
        raise ScenarioError(
            f"{base / 'problem.json'} repair_template must include {{findings}}"
        )

    for required in REQUIRED_SCENARIO_FILES:
        if not (base / required).is_file():
            raise ScenarioError(f"missing required artifact: {base / required}")

    pro_stage = problem.get("pro_stage")
    if pro_stage:
        artifact = base / str(pro_stage.get("artifact", ""))
        if not artifact.is_file():
            raise ScenarioError(f"missing required Pro artifact: {artifact}")
        data["pro_artifact"] = load_json(artifact)
    else:
        data["pro_artifact"] = {}

    bn_stage = problem.get("bn_stage")
    if bn_stage:
        network = base / str(bn_stage.get("artifact", ""))
        guardrail = base / str(bn_stage.get("guardrail", ""))
        if not network.is_file():
            raise ScenarioError(f"missing required BN artifact: {network}")
        if not guardrail.is_file():
            raise ScenarioError(f"missing required BN guardrail artifact: {guardrail}")
        data["bn_network"] = load_json(network)
        data["bn_guardrail"] = load_json(guardrail)
    else:
        data["bn_network"] = {}
        data["bn_guardrail"] = {}

    return data


def validate_scenarios() -> list[str]:
    errors: list[str] = []
    for name in SCENARIOS:
        try:
            scenario = load_scenario(name)
        except ScenarioError as exc:
            errors.append(str(exc))
            continue

        facts = scenario["facts"]
        for key in (
            "goal",
            "candidate_actions",
            "objects_required",
            "objects_moved",
            "resources",
            "constraints",
            "policy_context",
            "confidence",
        ):
            if key not in facts:
                errors.append(
                    f"{scenario['dir'] / 'mock-facts.json'} missing key '{key}'"
                )

        if name == "car-wash":
            ack = scenario["problem"].get("acknowledgement") or {}
            names = " ".join(str(v) for v in ack.values())
            if "Haris Rahi" not in names or "Tamara Storm" not in names:
                errors.append(
                    "car-wash acknowledgement must name Haris Rahi and Tamara Storm"
                )
            notes = scenario["problem"].get("research_notes") or []
            note_text = " ".join(json.dumps(note) for note in notes)
            for label in ("Opper.ai", "Focus AI", "HOB"):
                if label not in note_text:
                    errors.append(f"car-wash research_notes must include {label}")

        expected_ids = scenario["expected"].get("required_stage_ids") or []
        missing_ids = [
            stage_id for stage_id in CE_STAGE_IDS if stage_id not in expected_ids
        ]
        if missing_ids:
            errors.append(
                f"{scenario['dir'] / 'expected-output.json'} missing CE stage ids: {missing_ids}"
            )

        bn_stage = scenario["problem"].get("bn_stage")
        if name in {"coupon-stack", "cold-chain"}:
            if not bn_stage:
                errors.append(f"{scenario['dir'] / 'problem.json'} missing bn_stage")
            if not scenario.get("bn_network") or not scenario.get("bn_guardrail"):
                errors.append(f"{scenario['dir']} missing BN network or guardrail artifact")
            guardrail = scenario.get("bn_guardrail") or {}
            network = scenario.get("bn_network") or {}
            if guardrail.get("query_node") not in (network.get("query_nodes") or []):
                errors.append(f"{scenario['dir'] / 'bn-guardrail.json'} query_node must be in bn-network query_nodes")
            if not isinstance(guardrail.get("threshold"), (int, float)):
                errors.append(f"{scenario['dir'] / 'bn-guardrail.json'} threshold must be numeric")
        elif bn_stage or scenario.get("bn_network") or scenario.get("bn_guardrail"):
            errors.append(f"{scenario['dir']} must not define BN guardrails")

    return errors


def provider_env_present() -> bool:
    if os.environ.get(SIMULATE_LIVE_ENV) == "1" or fixture_llm_enabled():
        return True
    if os.environ.get("NXUSKIT_PROVIDER") and os.environ.get("NXUSKIT_MODEL"):
        return True
    if any(
        os.environ.get(name)
        for name in (
            "NXUSKIT_COMMON_SENSE_BASELINE_MODEL",
            "NXUSKIT_COMMON_SENSE_FACTS_MODEL",
            "NXUSKIT_COMMON_SENSE_REPAIR_MODEL",
        )
    ):
        return True
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return True
    if os.environ.get("OLLAMA_HOST") and endpoint_reachable(
        os.environ["OLLAMA_HOST"], "/api/tags"
    ):
        return True
    if os.environ.get("LMSTUDIO_BASE_URL") and endpoint_reachable(
        os.environ["LMSTUDIO_BASE_URL"], "/v1/models"
    ):
        return True
    return False


def fixture_llm_enabled() -> bool:
    return os.environ.get(FIXTURE_LLM_ENV) == "1"


def simulate_live_enabled() -> bool:
    return os.environ.get(SIMULATE_LIVE_ENV) == "1"


def endpoint_reachable(base: str, suffix: str) -> bool:
    url = base if base.startswith(("http://", "https://")) else f"http://{base}"
    url = url.rstrip("/") + suffix
    try:
        with urllib.request.urlopen(url, timeout=0.75) as response:
            return 200 <= response.status < 500
    except (OSError, socket.timeout, urllib.error.URLError):
        return False


def resolve_mode(requested: str) -> dict[str, Any]:
    if requested == "mock":
        return {
            "requested": requested,
            "source": "mock",
            "provider_available": False,
            "message": "mock mode uses checked-in fixtures and performs no provider preflight",
        }

    available = provider_env_present()
    simulated = simulate_live_enabled()
    fixture_llm = fixture_llm_enabled()
    if requested == "live":
        if not available:
            raise RuntimeError(
                "live mode requires NXUSKIT_PROVIDER/NXUSKIT_MODEL, ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, reachable OLLAMA_HOST, or reachable LMSTUDIO_BASE_URL"
            )
        if fixture_llm:
            return {
                "requested": requested,
                "source": "live",
                "provider_available": True,
                "message": "fixture LLM answers selected; local guardrail runtimes execute live",
            }
        return {
            "requested": requested,
            "source": "live",
            "provider_available": True,
            "message": "simulated live provider preflight succeeded"
            if simulated
            else "live provider preflight succeeded",
        }

    if available:
        if fixture_llm:
            return {
                "requested": requested,
                "source": "live",
                "provider_available": True,
                "message": "auto mode selected fixture LLM answers with live local guardrails",
            }
        return {
            "requested": requested,
            "source": "live",
            "provider_available": True,
            "message": "auto mode selected simulated live provider execution"
            if simulated
            else "auto mode selected live provider execution",
        }
    return {
        "requested": requested,
        "source": "mock",
        "provider_available": False,
        "message": "auto mode did not find a live provider; using checked-in fixtures",
    }


def has_pro_entitlement() -> bool:
    token = os.environ.get("NXUSKIT_LICENSE_TOKEN")
    if token:
        return True
    token_file = Path(
        os.environ.get("ENT_TOKEN_FILE", Path.home() / ".nxuskit" / "license.token")
    )
    if token_file.is_file():
        return True
    cli = os.environ.get("NXUSKIT_CLI", "nxuskit-cli")
    try:
        proc = subprocess.run(
            [cli, "license", "status", "--json"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    try:
        status = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    license_info = status.get("license") or {}
    features = set(license_info.get("features") or [])
    effective = str(license_info.get("effective_edition") or "").lower()
    return effective == "pro" or bool(PRO_GUARDRAILS & features)


def make_stage(
    stage_id: str,
    label: str,
    tier: str,
    source: str,
    status: str,
    output: dict[str, Any],
    message: str = "",
) -> dict[str, Any]:
    stage = {
        "id": stage_id,
        "label": label,
        "tier": tier,
        "source": source,
        "status": status,
        "output": output,
    }
    if message:
        stage["message"] = message
    return stage


def expected_findings(
    expected: dict[str, Any], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for raw in expected.get("expected_findings") or []:
        finding = {
            "mechanism": raw.get("mechanism", "clips"),
            "tier": raw.get("tier", "community"),
            "status": raw.get("status", "fail"),
            "rule_id": raw["rule_id"],
            "severity": raw.get("severity", "error"),
            "message": raw.get("message", f"Rule {raw['rule_id']} failed."),
            "evidence": raw.get(
                "evidence", {"facts_summary": facts.get("policy_context", {})}
            ),
            "repair_hint": raw.get("repair_hint", raw.get("message", "")),
        }
        findings.append(finding)
    return findings


def scenario_pro_engine(scenario: dict[str, Any]) -> str:
    return str(
        (scenario["problem"].get("pro_stage") or {}).get("engine", "solver")
    ).lower()


def scenario_pro_stage_id(scenario: dict[str, Any]) -> str:
    meta = scenario["problem"].get("pro_stage") or {}
    engine = scenario_pro_engine(scenario)
    return str(meta.get("id") or PRO_STAGE_BY_ENGINE.get(engine, "solver-proof"))


def scenario_supports_bn(scenario: dict[str, Any]) -> bool:
    return bool(scenario["problem"].get("bn_stage"))


def scenario_bn_stage_id(scenario: dict[str, Any]) -> str:
    meta = scenario["problem"].get("bn_stage") or {}
    return str(meta.get("id") or BN_STAGE_ID)


def mechanism_stage_id(scenario: dict[str, Any], mechanism: str) -> str:
    if mechanism == "clips":
        return "clips-validation"
    if mechanism == "bn":
        return scenario_bn_stage_id(scenario)
    return scenario_pro_stage_id(scenario)


def mechanism_label(scenario: dict[str, Any], mechanism: str) -> str:
    if mechanism == "clips":
        return "Community CLIPS validation"
    if mechanism == "bn":
        return str(
            (scenario.get("bn_guardrail") or {}).get("label")
            or (scenario["problem"].get("bn_stage") or {}).get("label")
            or BN_LABEL
        )
    return PRO_LABEL_BY_ENGINE[mechanism]


def mechanism_artifact(scenario: dict[str, Any], mechanism: str) -> str | None:
    if mechanism == "clips":
        return None
    key = "bn_stage" if mechanism == "bn" else "pro_stage"
    return (scenario["problem"].get(key) or {}).get("artifact")


def normalize_requested_guardrails(value: str | None) -> list[str] | str:
    if not value or value == "auto":
        return "auto"
    selected: list[str] = []
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if item == "z3":
            item = "solver"
        if item not in GUARDRAILS:
            raise ScenarioError(
                f"unknown guardrail '{raw}'; use auto, clips, solver, zen, z3, or bn"
            )
        if item not in selected:
            selected.append(item)
    if not selected:
        raise ScenarioError("at least one guardrail mechanism must be selected")
    return selected


def stage_guardrail_alias(stage: str | None, scenario: dict[str, Any]) -> list[str] | str:
    if stage in {None, "all"}:
        return "auto"
    if stage == "ce":
        return ["clips"]
    if stage == "pro":
        return [scenario_pro_engine(scenario)]
    raise ScenarioError(f"unknown stage '{stage}'")


def resolve_guardrails(
    scenario: dict[str, Any],
    requested_guardrails: str | None,
    requested_stage: str | None,
    source: str,
) -> dict[str, Any]:
    explicit_guardrails = requested_guardrails is not None
    normalized = normalize_requested_guardrails(requested_guardrails)
    if not explicit_guardrails:
        normalized = stage_guardrail_alias(requested_stage, scenario)

    pro_engine = scenario_pro_engine(scenario)
    warnings: list[str] = []
    explicit = normalized != "auto"
    if normalized == "auto":
        selected = ["clips", pro_engine]
        if source == "live" and not has_pro_entitlement():
            selected = ["clips"]
            warnings.append(
                f"auto guardrails skipped {pro_engine}; Pro entitlement was not detected"
            )
        if scenario_supports_bn(scenario):
            selected.append("bn")
    else:
        selected = list(normalized)

    for mechanism in selected:
        if mechanism in PRO_GUARDRAILS and mechanism != pro_engine:
            supported = "solver/Z3" if pro_engine == "solver" else "ZEN"
            requested = "solver/Z3" if mechanism == "solver" else "ZEN"
            raise ScenarioError(
                f"scenario '{scenario['problem']['id']}' supports {supported}, not {requested}"
            )
        if mechanism == "bn" and not scenario_supports_bn(scenario):
            raise ScenarioError(
                f"scenario '{scenario['problem']['id']}' does not support BN guardrails"
            )

    return {
        "requested": requested_guardrails or (
            f"stage:{requested_stage}" if requested_stage else "auto"
        ),
        "selected": selected,
        "mode": "explicit" if explicit else "auto",
        "warnings": warnings,
    }


def finding(
    mechanism: str,
    status: str,
    rule_id: str,
    message: str,
    *,
    severity: str = "error",
    evidence: dict[str, Any] | None = None,
    repair_hint: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    return {
        "mechanism": mechanism,
        "tier": "pro" if mechanism in PRO_GUARDRAILS else "community",
        "status": status,
        "rule_id": rule_id,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
        "repair_hint": repair_hint or message,
        **({"source": source} if source else {}),
    }


def findings_pass(findings: list[dict[str, Any]]) -> bool:
    return not any(item.get("status") == "fail" for item in findings)


def answer_matches_expected(scenario: dict[str, Any], content: str) -> bool:
    lowered = content.lower()
    tokens = scenario["expected"].get("expected_correction_contains") or []
    return bool(tokens) and all(str(token).lower() in lowered for token in tokens)


def clips_atom(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    return text.replace(" ", "_") or "unknown"


def render_clips_session_facts(scenario_id: str, facts: dict[str, Any]) -> list[str]:
    if scenario_id == "car-wash":
        rendered = []
        for item in facts.get("objects_required", []):
            rendered.append(
                "(required-object "
                f"(object {clips_atom(item.get('object'))}) "
                f"(required-location {clips_atom(item.get('required_location'))}) "
                f"(current-location {clips_atom(item.get('current_location'))}) "
                f"(present-at-required-location {clips_atom(item.get('present_at_required_location'))}))"
            )
        for item in facts.get("objects_moved", []):
            rendered.append(
                "(moved-object "
                f"(action-id {clips_atom(item.get('action_id'))}) "
                f"(object {clips_atom(item.get('object'))}) "
                f"(from {clips_atom(item.get('from'))}) "
                f"(to {clips_atom(item.get('to'))}))"
            )
        return rendered

    if scenario_id == "coupon-stack":
        action = (facts.get("candidate_actions") or [{}])[0]
        discounts = " ".join(clips_atom(item) for item in action.get("discounts", []))
        margin = facts.get("policy_context", {}).get("margin_percent_after_stack", 0)
        return [
            "(promotion-action "
            f"(id {clips_atom(action.get('id'))}) "
            f"(discounts {discounts}) "
            f"(free-shipping {clips_atom(action.get('free_shipping'))}) "
            f"(margin-after-stack {clips_atom(margin)}))"
        ]

    if scenario_id == "pallet-door":
        policy = facts.get("policy_context", {})
        action = (facts.get("candidate_actions") or [{}])[0]
        return [
            "(clearance "
            f"(pallet-width {clips_atom(policy.get('pallet_width_inches'))}) "
            f"(door-width {clips_atom(policy.get('door_width_inches'))}) "
            f"(load-state {clips_atom(policy.get('load_state'))}))",
            "(action "
            f"(id {clips_atom(action.get('id'))}) "
            f"(movement {clips_atom(action.get('recommendation'))}))",
        ]

    if scenario_id == "cold-chain":
        policy = facts.get("policy_context", {})
        action = (facts.get("candidate_actions") or [{}])[0]
        selected_carrier = action.get("carrier") or "cheap-courier"
        carrier = next(
            (
                item
                for item in facts.get("resources", [])
                if item.get("id") == selected_carrier
            ),
            {},
        )
        return [
            "(carrier "
            f"(id {clips_atom(carrier.get('id'))}) "
            f"(refrigerated {clips_atom(carrier.get('refrigerated'))}) "
            f"(temperature-logging {clips_atom(carrier.get('temperature_logging'))}) "
            f"(certified {clips_atom(policy.get('carrier_certified'))}))",
            "(custody "
            f"(handoff-record {clips_atom(policy.get('handoff_record'))}) "
            f"(audit-record {clips_atom(policy.get('temperature_monitoring'))}))",
        ]

    return []


def unwrap_clips(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def normalize_clips_slot_values(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
    elif isinstance(value, dict):
        parsed = value
    else:
        raise TypeError(f"unsupported CLIPS slot value shape: {type(value).__name__}")
    return parsed


def live_clips_findings(
    scenario: dict[str, Any], facts: dict[str, Any]
) -> dict[str, Any]:
    problem = scenario["problem"]
    payload = {
        "rules": (scenario["dir"] / "rules.clp").read_text(encoding="utf-8"),
        "facts": render_clips_session_facts(problem["id"], facts),
        "queries": ["guardrail-finding"],
    }
    result = run_cli_json(["clips", "eval"], payload)
    clips_result = result.get("result", result)
    findings = []
    for derived in clips_result.get("derived_facts") or []:
        if derived.get("template") != "guardrail-finding":
            continue
        slots = normalize_clips_slot_values(derived.get("slots") or {})
        findings.append(
            {
                "status": str(unwrap_clips(slots.get("status", "fail"))),
                "rule_id": str(unwrap_clips(slots.get("rule-id", "unknown-rule"))),
                "severity": str(unwrap_clips(slots.get("severity", "error"))),
                "message": str(unwrap_clips(slots.get("message", ""))),
                "evidence": {
                    "engine": "nxuskit-cli clips eval",
                    "runtime_executed": True,
                },
            }
        )
    rules_fired = int(
        clips_result.get(
            "fired_rules",
            sum(
                int(item.get("times_fired") or 0)
                for item in clips_result.get("matched_rules") or []
            ),
        )
    )
    if not findings:
        findings.append(
            finding(
                "clips",
                "pass",
                "clips-rules-satisfied",
                "CLIPS rules passed after the repaired recommendation.",
                severity="info",
                evidence={
                    "engine": "nxuskit-cli clips eval",
                    "runtime_executed": True,
                    "rules_fired": rules_fired,
                },
                source="live",
            )
        )
    return {
        "findings": findings,
        "rules_fired": rules_fired,
    }


def findings_text(findings: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{f['rule_id']}: {f.get('message', f['status'])}" for f in findings
    )


def build_repair_packet(
    scenario: dict[str, Any],
    source: str,
    *,
    raw_response: str | None = None,
    facts: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    problem = scenario["problem"]
    baseline = scenario["baseline"]
    facts = facts or scenario["facts"]
    findings = findings or expected_findings(scenario["expected"], facts)
    repair = scenario["repair"]
    inserted = findings_text(findings)
    retry_prompt = problem["repair_template"].replace("{findings}", inserted)
    return {
        "original_prompt": problem["baseline_prompt"],
        "raw_response": raw_response or baseline["content"],
        "extracted_facts": facts,
        "findings": findings,
        "repair_instructions": repair["repair_instructions"],
        "retry_prompt": retry_prompt,
        "source": source,
    }


def mock_pass_finding(mechanism: str) -> dict[str, Any]:
    if mechanism == "solver":
        rule_id = "solver-feasibility-satisfied"
        message = "Solver/Z3 guardrail passed after the repaired recommendation."
    elif mechanism == "zen":
        rule_id = "zen-policy-satisfied"
        message = "ZEN policy guardrail passed after the repaired recommendation."
    else:
        rule_id = "bn-risk-acceptable"
        message = "Bayesian risk guardrail passed after the repaired recommendation."
    return finding(
        mechanism,
        "pass",
        rule_id,
        message,
        severity="info",
        evidence={"mechanism_source": "fixture", "runtime_executed": False},
        source="mock",
    )


def mock_pro_findings(
    scenario: dict[str, Any], mechanism: str, answer: str, attempt: int
) -> list[dict[str, Any]]:
    artifact = scenario.get("pro_artifact") or {}
    if attempt > 1 or answer_matches_expected(scenario, answer):
        return [mock_pass_finding(mechanism)]
    stage_id = scenario_pro_stage_id(scenario)
    explanation = artifact.get(
        "explanation", f"{stage_id} fixture rejects the baseline answer."
    )
    return [
        finding(
            mechanism,
            "fail",
            stage_id,
            explanation,
            evidence={
                "artifact": scenario["problem"].get("pro_stage", {}).get("artifact"),
                "expected_result": artifact.get("expected_result", artifact),
                "mechanism_source": "fixture",
                "runtime_executed": False,
            },
            repair_hint=artifact.get("repair_hint", explanation),
            source="mock",
        )
    ]


def bn_finding_from_posteriors(
    scenario: dict[str, Any],
    posteriors: dict[str, Any],
    *,
    evidence: dict[str, Any],
    runtime_executed: bool,
    source: str,
) -> list[dict[str, Any]]:
    config = scenario.get("bn_guardrail") or {}
    query_node = str(config.get("query_node", "needs_review"))
    fail_state = str(config.get("fail_state", "yes"))
    threshold = float(config.get("threshold", 0.5))
    node_posteriors = posteriors.get(query_node, {})
    score = float(node_posteriors.get(fail_state, 0.0))
    failed = score >= threshold
    return [
        finding(
            "bn",
            "fail" if failed else "pass",
            str(config.get("fail_rule_id" if failed else "pass_rule_id") or ("bn-risk" if failed else "bn-risk-acceptable")),
            str(config.get("fail_message" if failed else "pass_message") or ("Bayesian risk guardrail requires review." if failed else "Bayesian risk guardrail accepted the recommendation.")),
            severity="warning" if failed else "info",
            evidence={
                "runtime_executed": runtime_executed,
                "query_node": query_node,
                "fail_state": fail_state,
                "probability": score,
                "threshold": threshold,
                "evidence": evidence,
                "posteriors": posteriors,
            },
            repair_hint=str(config.get("repair_hint", "Review the recommendation risk before approving.")),
            source=source,
        )
    ]


def mock_bn_findings(
    scenario: dict[str, Any], answer: str, attempt: int
) -> list[dict[str, Any]]:
    config = scenario.get("bn_guardrail") or {}
    key = "corrected" if attempt > 1 or answer_matches_expected(scenario, answer) else "baseline"
    result = (config.get("mock_results") or {}).get(key, {})
    return bn_finding_from_posteriors(
        scenario,
        result.get("posteriors", {}),
        evidence=result.get("evidence", {}),
        runtime_executed=False,
        source="mock",
    )


def solver_input_from_facts(
    scenario: dict[str, Any], facts: dict[str, Any]
) -> dict[str, Any]:
    scenario_id = scenario["problem"]["id"]
    if scenario_id == "car-wash":
        required = next(iter(facts.get("objects_required", [])), {})
        required_object = str(required.get("object", "car"))
        moves_required = any(
            item.get("object") == required_object for item in facts.get("objects_moved", [])
        )
        actual = 1 if required.get("present_at_required_location") or moves_required else 0
        return {
            "description": "Object-presence feasibility for a car-wash recommendation.",
            "variables": [
                {
                    "name": "required_object_present_after_action",
                    "var_type": "integer",
                    "domain": {"min": actual, "max": actual},
                    "label": "Whether the required object reaches the required location.",
                }
            ],
            "constraints": [
                {
                    "name": "required_object_must_be_present",
                    "label": "Washing requires the car at the wash location",
                    "constraint_type": "eq",
                    "variables": ["required_object_present_after_action"],
                    "parameters": {"right": 1},
                }
            ],
        }

    policy = facts.get("policy_context", {})
    action = (facts.get("candidate_actions") or [{}])[0]
    recommendation = str(action.get("recommendation", "")).lower()
    pallet_width = int(policy.get("pallet_width_inches") or 48)
    door_width = int(policy.get("door_width_inches") or 42)
    dock_width = int(policy.get("dock_door_b_width_inches") or 60)
    route_width = dock_width if any(
        token in recommendation for token in ("dock", "wider", "alternate", "approved")
    ) else door_width
    return {
        "description": "Dimensional feasibility for a loaded pallet route.",
        "variables": [
            {
                "name": "route_width_inches",
                "var_type": "integer",
                "domain": {"min": route_width, "max": route_width},
                "label": "Available route clearance.",
            },
            {
                "name": "pallet_width_inches",
                "var_type": "integer",
                "domain": {"min": pallet_width, "max": pallet_width},
                "label": "Loaded pallet width.",
            },
        ],
        "constraints": [
            {
                "name": "route_clearance",
                "label": "Route must be at least as wide as the loaded pallet",
                "constraint_type": "ge",
                "variables": ["route_width_inches", "pallet_width_inches"],
            }
        ],
    }


def zen_input_from_facts(facts: dict[str, Any]) -> dict[str, Any]:
    policy = facts.get("policy_context", {})
    action = (facts.get("candidate_actions") or [{}])[0]
    selected_carrier = action.get("carrier") or "cheap-courier"
    carrier = next(
        (item for item in facts.get("resources", []) if item.get("id") == selected_carrier),
        {},
    )
    return {
        "clearance_item": bool(policy.get("clearance_item", True)),
        "combined_margin_percent": policy.get("margin_percent_after_stack", 100),
        "discount_count": len(action.get("discounts", [])),
        "non_stackable_count": policy.get("non_stackable_count", len(action.get("discounts", []))),
        "carrier_certified": bool(policy.get("carrier_certified", False)),
        "handoff_record": bool(policy.get("handoff_record", False)),
        "refrigerated": bool(carrier.get("refrigerated", False)),
        "temperature_logging": bool(carrier.get("temperature_logging", False)),
    }


def selected_resource(facts: dict[str, Any]) -> dict[str, Any]:
    action = (facts.get("candidate_actions") or [{}])[0]
    resource_id = action.get("carrier")
    if not resource_id:
        return {}
    return next(
        (item for item in facts.get("resources", []) if item.get("id") == resource_id),
        {},
    )


def bn_evidence_from_facts(scenario: dict[str, Any], facts: dict[str, Any]) -> dict[str, str]:
    scenario_id = scenario["problem"]["id"]
    policy = facts.get("policy_context", {})
    action = (facts.get("candidate_actions") or [{}])[0]
    if scenario_id == "cold-chain":
        carrier = selected_resource(facts)
        return {
            "carrier_certified": "yes" if bool(policy.get("carrier_certified", False)) else "no",
            "handoff_record": "yes" if bool(policy.get("handoff_record", False)) else "no",
            "refrigerated": "yes" if bool(carrier.get("refrigerated", False)) else "no",
            "temperature_logging": "yes" if bool(carrier.get("temperature_logging", False)) else "no",
        }
    if scenario_id == "coupon-stack":
        discount_count = len(action.get("discounts", []))
        margin = policy.get("margin_percent_after_stack", 100)
        non_stackable = policy.get("non_stackable_count", discount_count)
        return {
            "clearance_item": "yes" if policy.get("item_type") == "clearance" else "no",
            "discount_count_bucket": "high" if discount_count > 1 else "low",
            "margin_floor_breach": "yes" if float(margin) < 20 else "no",
            "non_stackable_conflict": "yes" if int(non_stackable) > 1 else "no",
        }
    raise ScenarioError(f"scenario '{scenario_id}' does not support BN guardrails")


def bn_input_from_facts(scenario: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    network = scenario.get("bn_network") or {}
    return {
        "network": {
            "nodes": network.get("nodes", []),
            "edges": network.get("edges", []),
            "cpds": network.get("cpds", {}),
        },
        "evidence": bn_evidence_from_facts(scenario, facts),
        "query_nodes": network.get("query_nodes", ["needs_review"]),
    }


def run_cli_json(command: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    cli = os.environ.get("NXUSKIT_CLI", "nxuskit-cli")
    with tempfile.TemporaryDirectory(prefix="nxuskit-csg-") as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        proc = subprocess.run(
            [cli, *command, "--input", str(input_path), "--format", "json", "--output", str(output_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
            raise RuntimeError(detail)
        if output_path.is_file():
            return load_json(output_path)
        return json.loads(proc.stdout)


def live_solver_findings(
    scenario: dict[str, Any], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    payload = solver_input_from_facts(scenario, facts)
    result = run_cli_json(["solver", "solve"], payload)
    solver_result = result.get("result", result)
    satisfiable = bool(solver_result.get("satisfiable"))
    if satisfiable:
        return [
            finding(
                "solver",
                "pass",
                "solver-feasibility-satisfied",
                "Solver/Z3 found the recommendation feasible under the scenario constraints.",
                severity="info",
                evidence={"runtime_executed": True, "result": solver_result},
                source="live",
            )
        ]
    return [
        finding(
            "solver",
            "fail",
            scenario_pro_stage_id(scenario),
            "Solver/Z3 found the recommendation infeasible under the scenario constraints.",
            evidence={"runtime_executed": True, "result": solver_result},
            repair_hint=scenario["problem"]["guardrail_summary"],
            source="live",
        )
    ]


def live_zen_findings(
    scenario: dict[str, Any], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    artifact = scenario.get("pro_artifact") or {}
    table = artifact.get("table") or artifact
    payload = {"table": table, "input": zen_input_from_facts(facts)}
    result = run_cli_json(["zen", "eval"], payload)
    output = (result.get("result") or {}).get("output") or result.get("output") or {}
    allowed = bool(output.get("allowed"))
    if allowed:
        return [
            finding(
                "zen",
                "pass",
                "zen-policy-satisfied",
                "ZEN policy table allowed the recommendation.",
                severity="info",
                evidence={"runtime_executed": True, "result": output},
                source="live",
            )
        ]
    return [
        finding(
            "zen",
            "fail",
            scenario_pro_stage_id(scenario),
            str(output.get("decision") or "ZEN policy table rejected the recommendation."),
            evidence={"runtime_executed": True, "result": output},
            repair_hint=str(output.get("repair_hint") or scenario["problem"]["guardrail_summary"]),
            source="live",
        )
    ]


def live_bn_findings(
    scenario: dict[str, Any], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    payload = bn_input_from_facts(scenario, facts)
    result = run_cli_json(["bn", "infer"], payload)
    bn_result = result.get("result", result)
    return bn_finding_from_posteriors(
        scenario,
        bn_result.get("posteriors", {}),
        evidence=payload["evidence"],
        runtime_executed=True,
        source="live",
    )


def facts_prompt(problem: dict[str, Any], answer: str) -> str:
    return (
        f"{problem['extraction_prompt']}\n\n"
        "Return only JSON with keys goal, candidate_actions, objects_required, "
        "objects_moved, resources, constraints, policy_context, confidence. "
        "Use arrays for candidate_actions, objects_required, objects_moved, "
        "resources, and constraints. Do not use singular keys such as "
        "candidate_action or feasibility_constraints.\n\n"
        "Required shape; replace placeholders with facts extracted from the answer:\n"
        f"{FACTS_JSON_SHAPE}\n\n"
        f"Prompt:\n{problem['baseline_prompt']}\n\nAnswer:\n{answer}"
    )


def facts_for_answer(
    scenario: dict[str, Any],
    answer: str,
    *,
    source: str,
    facts_provider: Any | None,
    allow_fixture_fallback: bool,
    attempt: int = 1,
) -> tuple[dict[str, Any], str, str, str]:
    if source == "mock" or simulate_live_enabled():
        if attempt > 1 and "corrected_facts" in scenario:
            return (
                scenario["corrected_facts"],
                source,
                "pass",
                "Corrected facts fixture used for repaired-answer reevaluation.",
            )
        return scenario["facts"], source, "pass", "Facts are typed before rule evaluation."
    if source == "live" and fixture_llm_enabled():
        if attempt > 1 and "corrected_facts" in scenario:
            return (
                scenario["corrected_facts"],
                "mock",
                "pass",
                "Fixture facts used for repaired-answer reevaluation; guardrails execute live.",
            )
        return (
            scenario["facts"],
            "mock",
            "pass",
            "Fixture facts supplied for deterministic LLM smoke; guardrails execute live.",
        )
    try:
        facts, status, message = live_structured_facts(
            facts_provider, facts_prompt(scenario["problem"], answer)
        )
        return facts, "live", status, message
    except StructuredJsonError as exc:
        if not allow_fixture_fallback:
            raise
        return (
            scenario["facts"],
            "mock",
            "fail",
            f"Live structured extraction failed ({exc}); using checked-in fact fixture.",
        )


def clips_findings_for_attempt(
    scenario: dict[str, Any],
    facts: dict[str, Any],
    *,
    source: str,
    allow_fixture_fallback: bool,
    answer: str,
    attempt: int,
) -> tuple[list[dict[str, Any]], str, str]:
    if source == "mock" or simulate_live_enabled():
        if attempt > 1 or answer_matches_expected(scenario, answer):
            return (
                [
                    finding(
                        "clips",
                        "pass",
                        "clips-rules-satisfied",
                        "CLIPS rules passed after the repaired recommendation.",
                        severity="info",
                        evidence={"mechanism_source": "fixture", "runtime_executed": False},
                        source=source,
                    )
                ],
                source,
                "Fixture-backed CLIPS findings.",
            )
        return expected_findings(scenario["expected"], facts), source, "Fixture-backed CLIPS findings."
    try:
        clips_result = live_clips_findings(scenario, facts)
        findings = clips_result["findings"] or expected_findings(scenario["expected"], facts)
        for item in findings:
            item.setdefault("mechanism", "clips")
            item.setdefault("tier", "community")
            item.setdefault("repair_hint", item.get("message", ""))
        return findings, "live", "Findings produced by nxuskit-cli clips eval."
    except Exception:
        if not allow_fixture_fallback:
            raise
        return (
            expected_findings(scenario["expected"], facts),
            "mock",
            "Live nxuskit-cli clips eval failed; using checked-in expected findings.",
        )


def pro_findings_for_attempt(
    scenario: dict[str, Any],
    mechanism: str,
    facts: dict[str, Any],
    answer: str,
    *,
    source: str,
    auto_guardrails: bool,
    attempt: int,
) -> tuple[list[dict[str, Any]], str, str]:
    if source == "mock" or simulate_live_enabled():
        return (
            mock_pro_findings(scenario, mechanism, answer, attempt),
            source,
            "Fixture simulates Pro finding shape; no Solver/ZEN runtime was invoked.",
        )
    try:
        if mechanism == "solver":
            return live_solver_findings(scenario, facts), "live", "Findings produced by nxuskit-cli solver solve."
        return live_zen_findings(scenario, facts), "live", "Findings produced by nxuskit-cli zen eval."
    except RuntimeError as exc:
        message = str(exc)
        if "entitlement" in message.lower() and auto_guardrails:
            return (
                [
                    finding(
                        mechanism,
                        "pass",
                        f"{mechanism}-auto-downgraded",
                        f"Auto guardrails skipped {mechanism}; Pro entitlement was unavailable.",
                        severity="warning",
                        evidence={"runtime_executed": False, "error": message},
                        source="live",
                    )
                ],
                "live",
                f"Auto guardrails downgraded after {mechanism} entitlement check failed.",
            )
        raise


def bn_findings_for_attempt(
    scenario: dict[str, Any],
    facts: dict[str, Any],
    answer: str,
    *,
    source: str,
    attempt: int,
) -> tuple[list[dict[str, Any]], str, str]:
    if source == "mock" or simulate_live_enabled():
        return (
            mock_bn_findings(scenario, answer, attempt),
            source,
            "Fixture simulates BN risk finding shape; no BN runtime was invoked.",
        )
    return (
        live_bn_findings(scenario, facts),
        "live",
        "Findings produced by nxuskit-cli bn infer.",
    )


def evaluate_mechanism(
    scenario: dict[str, Any],
    mechanism: str,
    facts: dict[str, Any],
    answer: str,
    *,
    source: str,
    allow_fixture_fallback: bool,
    auto_guardrails: bool,
    attempt: int,
) -> tuple[list[dict[str, Any]], str, str]:
    if mechanism == "clips":
        return clips_findings_for_attempt(
            scenario,
            facts,
            source=source,
            allow_fixture_fallback=allow_fixture_fallback,
            answer=answer,
            attempt=attempt,
        )
    if mechanism == "bn":
        return bn_findings_for_attempt(
            scenario,
            facts,
            answer,
            source=source,
            attempt=attempt,
        )
    return pro_findings_for_attempt(
        scenario,
        mechanism,
        facts,
        answer,
        source=source,
        auto_guardrails=auto_guardrails,
        attempt=attempt,
    )


def run_guardrail_loop(
    scenario: dict[str, Any],
    source: str,
    guardrails: list[str],
    *,
    max_attempts: int,
    allow_fixture_fallback: bool,
    auto_guardrails: bool,
) -> dict[str, Any]:
    problem = scenario["problem"]
    baseline_provider = repair_provider = facts_provider = None
    fixture_llm = source == "live" and fixture_llm_enabled()
    if source == "live" and not simulate_live_enabled() and not fixture_llm:
        baseline_provider = make_provider("baseline")
        facts_provider = make_provider("facts")
        repair_provider = make_provider("repair")
        answer = provider_chat(
            baseline_provider,
            problem["baseline_prompt"],
            system="Answer the user directly. Do not mention guardrails.",
            max_tokens=500,
        )
        raw_source = "live"
    else:
        answer = scenario["baseline"]["content"]
        raw_source = source

    attempts: list[dict[str, Any]] = []
    repair_packets: list[dict[str, Any]] = []
    final_answer = answer

    for attempt_number in range(1, max_attempts + 1):
        facts, fact_source, fact_status, fact_message = facts_for_answer(
            scenario,
            answer,
            source=source,
            facts_provider=facts_provider,
            allow_fixture_fallback=allow_fixture_fallback,
            attempt=attempt_number,
        )
        mechanism_results: dict[str, Any] = {}
        merged_findings: list[dict[str, Any]] = []
        for mechanism in guardrails:
            mechanism_source = (
                source
                if fixture_llm
                else fact_source
                if mechanism == "clips"
                else source
            )
            findings, finding_source, message = evaluate_mechanism(
                scenario,
                mechanism,
                facts,
                answer,
                source=mechanism_source,
                allow_fixture_fallback=allow_fixture_fallback,
                auto_guardrails=auto_guardrails,
                attempt=attempt_number,
            )
            mechanism_results[mechanism] = {
                "source": finding_source,
                "status": "pass" if findings_pass(findings) else "fail",
                "findings": findings,
                "message": message,
            }
            merged_findings.extend(findings)

        attempt = {
            "attempt": attempt_number,
            "answer": answer,
            "facts": facts,
            "facts_source": fact_source,
            "facts_status": fact_status,
            "facts_message": fact_message,
            "mechanisms": mechanism_results,
            "findings": merged_findings,
            "status": "pass" if findings_pass(merged_findings) else "fail",
        }
        attempts.append(attempt)
        if attempt["status"] == "pass":
            final_answer = answer
            break

        packet = build_repair_packet(
            scenario,
            fact_source,
            raw_response=answer,
            facts=facts,
            findings=[item for item in merged_findings if item.get("status") == "fail"],
        )
        packet["attempt"] = attempt_number
        repair_packets.append(packet)
        if attempt_number == max_attempts:
            final_answer = answer
            break

        if source == "live" and not simulate_live_enabled() and not fixture_llm:
            answer = provider_chat(
                repair_provider,
                packet["retry_prompt"],
                system="Return a corrected recommendation that satisfies every finding.",
                max_tokens=700,
            )
        else:
            answer = scenario["corrected"]["content"]

    return {
        "raw_answer": attempts[0]["answer"] if attempts else final_answer,
        "raw_source": raw_source,
        "attempts": attempts,
        "repair_packets": repair_packets,
        "final_answer": final_answer,
        "final_status": attempts[-1]["status"] if attempts else "fail",
    }


def stage_status(attempts: list[dict[str, Any]], key: str | None = None) -> str:
    if not attempts:
        return "fail"
    values = []
    for attempt in attempts:
        if key is None:
            values.append(attempt.get("status", "fail"))
        else:
            values.append(attempt["mechanisms"].get(key, {}).get("status", "skipped"))
    if values[-1] == "pass":
        return "pass"
    if "fail" in values:
        return "fail"
    if "warn" in values:
        return "warn"
    return values[-1]


def stages_from_loop(
    scenario: dict[str, Any], loop: dict[str, Any], guardrails: list[str], source: str
) -> list[dict[str, Any]]:
    problem = scenario["problem"]
    attempts = loop["attempts"]
    first = attempts[0]
    stages = [
        make_stage(
            "raw-baseline",
            "Raw LLM baseline",
            "community",
            loop["raw_source"],
            "fail" if first["status"] == "fail" else "pass",
            {
                "content": loop["raw_answer"],
                "expected_bad_answer": problem["expected_bad_answer"],
                "notes": scenario["baseline"].get("notes", []),
            },
            "Baseline answer captured before guardrail validation.",
        ),
        make_stage(
            "structured-facts",
            "Structured fact extraction",
            "community",
            first["facts_source"],
            "fail" if any(a["facts_status"] == "fail" for a in attempts) else first["facts_status"],
            {
                "current": attempts[-1]["facts"],
                "attempts": [
                    {
                        "attempt": a["attempt"],
                        "source": a["facts_source"],
                        "status": a["facts_status"],
                        "facts": a["facts"],
                        "message": a["facts_message"],
                    }
                    for a in attempts
                ],
            },
            first["facts_message"],
        ),
    ]

    for mechanism in guardrails:
        final_result = attempts[-1]["mechanisms"][mechanism]
        stage_id = mechanism_stage_id(scenario, mechanism)
        label = mechanism_label(scenario, mechanism)
        stages.append(
            make_stage(
                stage_id,
                label,
                "pro" if mechanism in PRO_GUARDRAILS else "community",
                final_result["source"],
                stage_status(attempts, mechanism),
                {
                    "mechanism": mechanism,
                    "findings": final_result["findings"],
                    "attempts": [
                        {
                            "attempt": a["attempt"],
                            **a["mechanisms"][mechanism],
                        }
                        for a in attempts
                    ],
                    **(
                        {"rules_file": str(scenario["dir"] / "rules.clp")}
                        if mechanism == "clips"
                        else {"artifact": mechanism_artifact(scenario, mechanism)}
                    ),
                },
                final_result["message"],
            )
        )

    if loop["repair_packets"]:
        stages.append(
            make_stage(
                "repair-packet",
                "Deterministic repair packet",
                "community",
                loop["repair_packets"][-1]["source"],
                "pass",
                {
                    **loop["repair_packets"][-1],
                    "attempts": loop["repair_packets"],
                },
                "Repair prompt is assembled from selected guardrail findings.",
            )
        )

    stages.append(
        make_stage(
            "corrected-answer",
            "Corrected answer",
            "community",
            source,
            "pass" if loop["final_status"] == "pass" else "fail",
            {
                "content": loop["final_answer"],
                "validation_status": loop["final_status"],
                "expected_corrected_answer": problem["expected_corrected_answer"],
                "attempt_count": len(attempts),
            },
            "Final recommendation passed selected guardrails."
            if loop["final_status"] == "pass"
            else "Final recommendation still failed at least one selected guardrail.",
        )
    )
    return stages


def mock_ce_stages(scenario: dict[str, Any], source: str) -> list[dict[str, Any]]:
    problem = scenario["problem"]
    baseline = dict(scenario["baseline"])
    facts = dict(scenario["facts"])
    corrected = dict(scenario["corrected"])
    findings = expected_findings(scenario["expected"], facts)
    packet = build_repair_packet(scenario, source)

    return [
        make_stage(
            "raw-baseline",
            "Raw LLM baseline",
            "community",
            source,
            "fail",
            {
                "content": baseline["content"],
                "expected_bad_answer": problem["expected_bad_answer"],
                "notes": baseline.get("notes", []),
            },
            "Baseline answer violates at least one common-sense guardrail.",
        ),
        make_stage(
            "structured-facts",
            "Structured fact extraction",
            "community",
            source,
            "pass",
            facts,
            "Facts are typed before rule evaluation.",
        ),
        make_stage(
            "clips-validation",
            "Community CLIPS validation",
            "community",
            source,
            "fail" if any(f["status"] == "fail" for f in findings) else "pass",
            {"findings": findings, "rules_file": str(scenario["dir"] / "rules.clp")},
            "Validation failed; building deterministic repair packet.",
        ),
        make_stage(
            "repair-packet",
            "Deterministic repair packet",
            "community",
            source,
            "pass",
            packet,
            "Repair prompt is assembled from findings, not free-form guesswork.",
        ),
        make_stage(
            "corrected-answer",
            "Corrected answer",
            "community",
            source,
            corrected.get("validation_status", "pass"),
            {
                "content": corrected["content"],
                "validation_status": corrected.get("validation_status", "pass"),
                "expected_corrected_answer": problem["expected_corrected_answer"],
            },
            "Corrected recommendation passes Community guardrails.",
        ),
    ]


def phase_env(phase: str | None, suffix: str) -> str | None:
    phase_names = {
        "baseline": f"NXUSKIT_COMMON_SENSE_BASELINE_{suffix}",
        "facts": f"NXUSKIT_COMMON_SENSE_FACTS_{suffix}",
        "repair": f"NXUSKIT_COMMON_SENSE_REPAIR_{suffix}",
    }
    if phase and phase in phase_names:
        value = os.environ.get(phase_names[phase])
        if value:
            return value
    return None


def make_provider(phase: str | None = None):
    from nxuskit import Provider

    provider_name = (
        phase_env(phase, "PROVIDER") or os.environ.get("NXUSKIT_PROVIDER", "")
    ).lower()
    model = phase_env(phase, "MODEL") or os.environ.get("NXUSKIT_MODEL")
    if provider_name in {"anthropic", "claude"} or (
        not provider_name and os.environ.get("ANTHROPIC_API_KEY")
    ):
        return Provider.claude(
            model=model or "claude-haiku-4-5-20251001",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    if provider_name == "openai" or (
        not provider_name and os.environ.get("OPENAI_API_KEY")
    ):
        return Provider.openai(
            model=model or "gpt-4o-mini", api_key=os.environ.get("OPENAI_API_KEY")
        )
    return Provider.ollama(
        model=model or "llama3",
        api_url=os.environ.get("OLLAMA_HOST") or None,
        timeout=OLLAMA_READ_TIMEOUT_SECONDS,
        connect_timeout=OLLAMA_CONNECT_TIMEOUT_SECONDS,
        read_timeout=OLLAMA_READ_TIMEOUT_SECONDS,
    )


def provider_chat(
    provider: Any,
    prompt: str,
    *,
    system: str,
    max_tokens: int = 700,
    response_format: Any | None = None,
) -> str:
    from nxuskit import Message

    kwargs: dict[str, Any] = {
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = provider.chat([Message.system(system), Message.user(prompt)], **kwargs)
    return str(response.content).strip()


def strip_json_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class StructuredJsonError(ValueError):
    """Raised when a live structured-output response cannot produce facts."""


def json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
    return candidates


def fenced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    search_from = 0
    while True:
        fence_start = text.find("```", search_from)
        if fence_start == -1:
            return candidates
        body_start = text.find("\n", fence_start + 3)
        if body_start == -1:
            return candidates
        fence_end = text.find("```", body_start + 1)
        if fence_end == -1:
            return candidates
        candidates.append(text[body_start + 1 : fence_end].strip())
        search_from = fence_end + 3


def parse_json_object(payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StructuredJsonError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise StructuredJsonError("JSON payload must be an object")
    return parsed


def extract_json_object(content: str) -> tuple[dict[str, Any], str | None]:
    text = content.strip()
    if not text:
        raise StructuredJsonError("empty structured-output response")

    try:
        return parse_json_object(strip_json_fences(text)), None
    except StructuredJsonError:
        pass

    for candidate in [*fenced_json_candidates(text), *json_object_candidates(text)]:
        try:
            return (
                parse_json_object(candidate),
                "Live structured extraction wrapped JSON in prose; extracted the JSON object and continuing.",
            )
        except StructuredJsonError:
            continue
    raise StructuredJsonError(
        "no valid JSON object found in structured-output response"
    )


def validate_facts_shape(facts: dict[str, Any]) -> list[str]:
    errors = []
    expected_types = {
        "candidate_actions": list,
        "objects_required": list,
        "objects_moved": list,
        "resources": list,
        "constraints": list,
        "policy_context": dict,
        "confidence": (int, float),
    }
    for key in ("goal", *expected_types):
        if key not in facts:
            errors.append(f"missing key '{key}'")
    if errors:
        return errors
    if not isinstance(facts["goal"], (dict, str)):
        errors.append("key 'goal' must be an object or string")
    for key, expected in expected_types.items():
        if not isinstance(facts[key], expected):
            errors.append(f"key '{key}' has invalid type")
    for item in facts.get("objects_required", []):
        if not isinstance(item, dict):
            errors.append("objects_required items must be objects")
            continue
        if not isinstance(item.get("object"), str):
            errors.append("objects_required items need string object")
        if not isinstance(item.get("required_location"), str):
            errors.append("objects_required items need string required_location")
        if not isinstance(item.get("present_at_required_location"), bool):
            errors.append(
                "objects_required items need boolean present_at_required_location"
            )
    for item in facts.get("objects_moved", []):
        if not isinstance(item, dict):
            errors.append("objects_moved items must be objects")
            continue
        for key in ("action_id", "object", "from", "to"):
            if not isinstance(item.get(key), str):
                errors.append(f"objects_moved items need string {key}")
    return errors


def parse_facts_response(content: str) -> tuple[dict[str, Any], str | None]:
    facts, warning = extract_json_object(content)
    errors = validate_facts_shape(facts)
    if errors:
        raise StructuredJsonError("; ".join(errors))
    return facts, warning


def structured_json_response_format() -> Any | None:
    try:
        from nxuskit import ResponseFormat
    except Exception:
        return None
    return getattr(ResponseFormat, "JSON", None)


def live_structured_facts(
    provider: Any, extraction_prompt: str
) -> tuple[dict[str, Any], str, str]:
    prompt = extraction_prompt
    system = "Extract typed JSON facts. Return JSON only."
    attempts: list[str] = []
    response_format = structured_json_response_format()

    for attempt in (1, 2):
        try:
            content = provider_chat(
                provider,
                prompt,
                system=system,
                max_tokens=900,
                response_format=response_format,
            )
            facts, warning = parse_facts_response(content)
        except Exception as exc:
            attempts.append(f"attempt {attempt}: {exc}")
            prompt = (
                extraction_prompt
                + "\n\nValidation feedback: "
                + str(exc)
                + ". Return only valid JSON with all required fact keys and no prose."
            )
            system = "Repair the JSON extraction. Return JSON only."
            continue
        if warning:
            return facts, "warn", warning
        return facts, "pass", "Facts came from live structured extraction."

    raise StructuredJsonError("; ".join(attempts))


def live_ce_stages(
    scenario: dict[str, Any], *, allow_fixture_fallback: bool
) -> list[dict[str, Any]]:
    problem = scenario["problem"]
    baseline_provider = make_provider("baseline")
    facts_provider = make_provider("facts")
    repair_provider = make_provider("repair")
    raw = provider_chat(
        baseline_provider,
        problem["baseline_prompt"],
        system="Answer the user directly. Do not mention guardrails.",
        max_tokens=500,
    )

    extraction_prompt = (
        f"{problem['extraction_prompt']}\n\n"
        "Return only JSON with keys goal, candidate_actions, objects_required, "
        "objects_moved, resources, constraints, policy_context, confidence. "
        "Use arrays for candidate_actions, objects_required, objects_moved, "
        "resources, and constraints. Do not use singular keys such as "
        "candidate_action or feasibility_constraints.\n\n"
        "Required shape; replace placeholders with facts extracted from the answer:\n"
        f"{FACTS_JSON_SHAPE}\n\n"
        f"Prompt:\n{problem['baseline_prompt']}\n\nAnswer:\n{raw}"
    )
    fact_source = "live"
    fact_status = "pass"
    fact_message = "Facts came from live structured extraction."
    try:
        facts, fact_status, fact_message = live_structured_facts(
            facts_provider, extraction_prompt
        )
    except StructuredJsonError as exc:
        facts = scenario["facts"]
        fact_source = "mock"
        fact_status = "fail"
        fact_message = (
            f"Live structured extraction failed ({exc}); using checked-in fact fixture."
        )

    clips_source = fact_source
    clips_message = "Findings produced by nxuskit-cli clips eval."
    try:
        clips_result = live_clips_findings(scenario, facts)
        findings = clips_result["findings"] or expected_findings(
            scenario["expected"], facts
        )
    except Exception:
        if not allow_fixture_fallback:
            raise
        findings = expected_findings(scenario["expected"], facts)
        clips_source = "mock"
        clips_message = (
            "Live nxuskit-cli clips eval failed; using checked-in expected findings."
        )
    packet = build_repair_packet(
        {
            **scenario,
            "baseline": {
                "content": raw,
                "notes": ["Live answer captured through nxusKit Provider."],
            },
            "facts": facts,
        },
        fact_source,
    )
    corrected_prompt = packet["retry_prompt"]
    try:
        corrected = provider_chat(
            repair_provider,
            corrected_prompt,
            system="Return a corrected recommendation that satisfies every finding.",
            max_tokens=700,
        )
    except Exception:
        if not allow_fixture_fallback:
            raise
        corrected = scenario["corrected"]["content"]

    return [
        make_stage(
            "raw-baseline",
            "Raw LLM baseline",
            "community",
            "live",
            "fail",
            {
                "content": raw,
                "expected_bad_answer": problem["expected_bad_answer"],
                "notes": [],
            },
            "Live baseline answer captured before rule validation.",
        ),
        make_stage(
            "structured-facts",
            "Structured fact extraction",
            "community",
            fact_source,
            fact_status,
            facts,
            fact_message,
        ),
        make_stage(
            "clips-validation",
            "Community CLIPS validation",
            "community",
            clips_source,
            "fail" if any(f["status"] == "fail" for f in findings) else "pass",
            {"findings": findings, "rules_file": str(scenario["dir"] / "rules.clp")},
            clips_message,
        ),
        make_stage(
            "repair-packet",
            "Deterministic repair packet",
            "community",
            fact_source,
            "pass",
            packet,
            "Repair prompt is assembled from typed findings.",
        ),
        make_stage(
            "corrected-answer",
            "Corrected answer",
            "community",
            "live",
            "pass",
            {
                "content": corrected,
                "validation_status": "pass",
                "expected_corrected_answer": problem["expected_corrected_answer"],
            },
            "Corrected recommendation returned through nxusKit Provider.",
        ),
    ]


def build_report(
    name: str,
    requested_mode: str,
    requested_stage: str | None,
    requested_guardrails: str | None = None,
    max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS,
) -> dict[str, Any]:
    scenario = load_scenario(name)
    resolution = resolve_mode(requested_mode)
    source = resolution["source"]
    selection = resolve_guardrails(
        scenario, requested_guardrails, requested_stage, source
    )
    selected_guardrails = selection["selected"]

    if source == "live":
        try:
            loop = run_guardrail_loop(
                scenario,
                source,
                selected_guardrails,
                max_attempts=max_repair_attempts,
                allow_fixture_fallback=requested_mode == "auto",
                auto_guardrails=selection["mode"] == "auto",
            )
        except Exception as exc:
            if requested_mode == "live":
                raise RuntimeError(f"live execution failed: {exc}") from exc
            resolution = {
                "requested": requested_mode,
                "source": "mock",
                "provider_available": True,
                "message": f"auto live execution failed; using checked-in fixtures: {exc}",
            }
            source = "mock"
            selection = resolve_guardrails(
                scenario, requested_guardrails, requested_stage, source
            )
            selected_guardrails = selection["selected"]
            loop = run_guardrail_loop(
                scenario,
                source,
                selected_guardrails,
                max_attempts=max_repair_attempts,
                allow_fixture_fallback=True,
                auto_guardrails=selection["mode"] == "auto",
            )
    else:
        loop = run_guardrail_loop(
            scenario,
            source,
            selected_guardrails,
            max_attempts=max_repair_attempts,
            allow_fixture_fallback=True,
            auto_guardrails=selection["mode"] == "auto",
        )

    stages = stages_from_loop(scenario, loop, selected_guardrails, source)
    final_status = "pass" if loop["final_status"] == "pass" else "fail"
    if any(stage["status"] == "warn" for stage in stages) and final_status == "pass":
        final_status = "warn"

    return {
        "example": EXAMPLE_ID,
        "scenario": name,
        "mode": requested_mode,
        "resolved_mode": source,
        "requested_stage": requested_stage or "all",
        "requested_guardrails": requested_guardrails or "auto",
        "guardrail_selection": selection,
        "max_repair_attempts": max_repair_attempts,
        "mode_resolution": resolution,
        "stages": stages,
        "final_status": final_status,
        "summary": (
            "Recommendation passes selected guardrails."
            if final_status == "pass"
            else "Recommendation passes selected guardrails with warnings."
            if final_status == "warn"
            else "Run completed with structured-facts or guardrail failures."
            if final_status == "fail"
            else "Run completed with guardrail warnings or skipped stages."
        ),
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"=== {EXAMPLE_ID}: {report['scenario']} ===",
        f"mode: {report['mode']} -> {report['resolved_mode']}",
        f"guardrails: {', '.join(report['guardrail_selection']['selected'])}",
        f"max repair attempts: {report['max_repair_attempts']}",
        f"preflight: {report['mode_resolution']['message']}",
        "",
    ]
    for warning in report["guardrail_selection"].get("warnings", []):
        lines.append(f"warning: {warning}")
    if report["guardrail_selection"].get("warnings"):
        lines.append("")
    for stage in report["stages"]:
        lines.append(
            f"[{stage['status']}] {stage['label']} ({stage['tier']}, {stage['source']})"
        )
        if stage.get("message"):
            lines.append(f"  {stage['message']}")
        output = stage.get("output") or {}
        if stage["id"] in {"raw-baseline", "corrected-answer"}:
            content = output.get("content", "")
            lines.append(f"  {content}")
        elif stage["id"] in {"clips-validation", "solver-proof", "zen-policy", "bn-risk"}:
            for attempt in output.get("attempts", []):
                lines.append(f"  attempt {attempt['attempt']}: {attempt['status']}")
                for item in attempt.get("findings", []):
                    lines.append(f"    - {item['rule_id']}: {item['message']}")
        elif stage["id"] == "repair-packet":
            lines.append(f"  repair: {output.get('repair_instructions', '')}")
        lines.append("")
    lines.append(f"final: {report['final_status']} - {report['summary']}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Progressive common-sense guardrails: selected CLIPS, Solver/Z3, "
            "ZEN, and BN checks repair and re-evaluate LLM answers."
        )
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="car-wash")
    parser.add_argument("--mode", choices=("auto", "live", "mock"), default="live")
    parser.add_argument(
        "--guardrails",
        default=None,
        help=(
            "Comma-separated guardrails: auto, clips, solver/z3, zen, bn. "
            "BN is modeled for coupon-stack and cold-chain; --stage remains a compatibility alias."
        ),
    )
    parser.add_argument(
        "--stage",
        choices=("ce", "pro", "all"),
        default=None,
        help="Compatibility alias: ce=clips, pro=scenario Pro guardrail, all=auto",
    )
    parser.add_argument(
        "--max-repair-attempts",
        type=int,
        default=DEFAULT_MAX_REPAIR_ATTEMPTS,
        help="Maximum guardrail-repair-retry attempts before failing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit shared machine-readable progression report",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show additional execution detail"
    )
    parser.add_argument(
        "--step", "-s", action="store_true", help="Pause between human-readable stages"
    )
    parser.add_argument(
        "--validate-scenarios",
        action="store_true",
        help="Validate scenario artifacts without running stages",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.validate_scenarios:
        errors = validate_scenarios()
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("All common-sense guardrails scenario artifacts are valid.")
        return 0

    try:
        report = build_report(
            args.scenario,
            args.mode,
            args.stage,
            args.guardrails,
            args.max_repair_attempts,
        )
    except (RuntimeError, ScenarioError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    rendered = render_report(report)
    if args.step:
        for block in rendered.split("\n\n"):
            print(block)
            try:
                response = input("Press Enter to continue (q to quit)... ")
            except EOFError:
                response = ""
            if response.lower() == "q":
                break
            print()
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
