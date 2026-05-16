#!/usr/bin/env python3
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
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EXAMPLE_ID = "common-sense-guardrails"
SCENARIOS = ("car-wash", "coupon-stack", "pallet-door", "cold-chain")
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
    "mock-repair.json",
    "mock-corrected.json",
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "scenarios"


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

    return errors


def provider_env_present() -> bool:
    if os.environ.get("NXUSKIT_COMMON_SENSE_SIMULATE_LIVE") == "1":
        return True
    if os.environ.get("NXUSKIT_PROVIDER") and os.environ.get("NXUSKIT_MODEL"):
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
    simulated = os.environ.get("NXUSKIT_COMMON_SENSE_SIMULATE_LIVE") == "1"
    if requested == "live":
        if not available:
            raise RuntimeError(
                "live mode requires NXUSKIT_PROVIDER/NXUSKIT_MODEL, ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, reachable OLLAMA_HOST, or reachable LMSTUDIO_BASE_URL"
            )
        return {
            "requested": requested,
            "source": "live",
            "provider_available": True,
            "message": "simulated live provider preflight succeeded"
            if simulated
            else "live provider preflight succeeded",
        }

    if available:
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
    return token_file.is_file()


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
            "status": raw.get("status", "fail"),
            "rule_id": raw["rule_id"],
            "severity": raw.get("severity", "error"),
            "message": raw.get("message", f"Rule {raw['rule_id']} failed."),
            "evidence": raw.get(
                "evidence", {"facts_summary": facts.get("policy_context", {})}
            ),
        }
        findings.append(finding)
    return findings


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
        carrier = next(
            (
                item
                for item in facts.get("resources", [])
                if item.get("id") == "cheap-courier"
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


def live_clips_findings(
    scenario: dict[str, Any], facts: dict[str, Any]
) -> dict[str, Any]:
    from nxuskit import ClipsSession

    problem = scenario["problem"]
    with ClipsSession() as clips:
        clips.load_file(str(scenario["dir"] / "rules.clp"))
        clips.reset()
        for fact in render_clips_session_facts(problem["id"], facts):
            clips.fact_assert_string(fact)
        rules_fired = clips.run()
        fact_indices = clips.facts_by_template("guardrail-finding")
        findings = []
        for fact_index in fact_indices:
            slots = json.loads(clips.fact_slot_values(fact_index))
            findings.append(
                {
                    "status": str(unwrap_clips(slots.get("status", "fail"))),
                    "rule_id": str(unwrap_clips(slots.get("rule-id", "unknown-rule"))),
                    "severity": str(unwrap_clips(slots.get("severity", "error"))),
                    "message": str(unwrap_clips(slots.get("message", ""))),
                    "evidence": {"engine": "ClipsSession", "fact_index": fact_index},
                }
            )
        return {"findings": findings, "rules_fired": rules_fired}


def findings_text(findings: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{f['rule_id']}: {f.get('message', f['status'])}" for f in findings
    )


def build_repair_packet(scenario: dict[str, Any], source: str) -> dict[str, Any]:
    problem = scenario["problem"]
    baseline = scenario["baseline"]
    facts = scenario["facts"]
    findings = expected_findings(scenario["expected"], facts)
    repair = scenario["repair"]
    inserted = findings_text(findings)
    retry_prompt = repair.get("retry_prompt") or problem["repair_template"].replace(
        "{findings}", inserted
    )
    return {
        "original_prompt": problem["baseline_prompt"],
        "raw_response": baseline["content"],
        "extracted_facts": facts,
        "findings": findings,
        "repair_instructions": repair["repair_instructions"],
        "retry_prompt": retry_prompt,
        "source": source,
    }


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


def make_provider():
    from nxuskit import Provider

    provider_name = os.environ.get("NXUSKIT_PROVIDER", "").lower()
    model = os.environ.get("NXUSKIT_MODEL")
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
    return Provider.ollama(model=model or "llama3")


def provider_chat(
    provider: Any, prompt: str, *, system: str, max_tokens: int = 700
) -> str:
    from nxuskit import Message

    response = provider.chat(
        [Message.system(system), Message.user(prompt)],
        temperature=0.1,
        max_tokens=max_tokens,
    )
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
            errors.append(f"missing key '{key}'")
    return errors


def parse_facts_response(content: str) -> tuple[dict[str, Any], str | None]:
    facts, warning = extract_json_object(content)
    errors = validate_facts_shape(facts)
    if errors:
        raise StructuredJsonError("; ".join(errors))
    return facts, warning


def live_structured_facts(
    provider: Any, extraction_prompt: str
) -> tuple[dict[str, Any], str, str]:
    prompt = extraction_prompt
    system = "Extract typed JSON facts. Return JSON only."
    attempts: list[str] = []

    for attempt in (1, 2):
        try:
            content = provider_chat(provider, prompt, system=system, max_tokens=900)
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
    provider = make_provider()
    raw = provider_chat(
        provider,
        problem["baseline_prompt"],
        system="Answer the user directly. Do not mention guardrails.",
        max_tokens=500,
    )

    extraction_prompt = (
        f"{problem['extraction_prompt']}\n\n"
        "Return only JSON with keys goal, candidate_actions, objects_required, "
        "objects_moved, resources, constraints, policy_context, confidence.\n\n"
        f"Prompt:\n{problem['baseline_prompt']}\n\nAnswer:\n{raw}"
    )
    fact_source = "live"
    fact_status = "pass"
    fact_message = "Facts came from live structured extraction."
    try:
        facts, fact_status, fact_message = live_structured_facts(
            provider, extraction_prompt
        )
    except StructuredJsonError as exc:
        facts = scenario["facts"]
        fact_source = "mock"
        fact_status = "warn"
        fact_message = (
            f"Live structured extraction failed ({exc}); using checked-in fact fixture."
        )

    clips_source = fact_source
    clips_message = "Findings produced through nxusKit ClipsSession."
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
            "Live ClipsSession validation failed; using checked-in expected findings."
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
            provider,
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


def pro_stage(scenario: dict[str, Any], source: str) -> dict[str, Any]:
    problem = scenario["problem"]
    stage_meta = problem.get("pro_stage") or {}
    stage_id = stage_meta.get("id", "solver-proof")
    engine = stage_meta.get("engine", "solver")
    label = "Solver proof" if engine == "solver" else "ZEN policy table"

    if source == "live" and not has_pro_entitlement():
        return make_stage(
            stage_id,
            label,
            "pro",
            "live",
            "skipped",
            {
                "engine": engine,
                "entitlement_mode": "unavailable",
                "result": {},
                "explanation": "Live Pro evidence requires a Pro entitlement; Community stages remain runnable.",
            },
            "Pro entitlement unavailable; skipping live Pro stage.",
        )

    artifact = scenario.get("pro_artifact") or {}
    return make_stage(
        stage_id,
        label,
        "pro",
        source,
        "pass",
        {
            "engine": engine,
            "entitlement_mode": "mock-fixture" if source == "mock" else "live-entitled",
            "result": artifact.get("expected_result", artifact),
            "artifact": stage_meta.get("artifact"),
            "explanation": artifact.get(
                "explanation",
                "Pro evidence fixture supports the corrected recommendation.",
            ),
        },
        "Mock Pro evidence uses checked-in Solver/ZEN artifacts and requires no entitlement."
        if source == "mock"
        else "Live Pro evidence entitlement check passed.",
    )


def build_report(
    name: str, requested_mode: str, requested_stage: str
) -> dict[str, Any]:
    scenario = load_scenario(name)
    resolution = resolve_mode(requested_mode)
    source = resolution["source"]

    if source == "live" and os.environ.get("NXUSKIT_COMMON_SENSE_SIMULATE_LIVE") == "1":
        ce_stages = mock_ce_stages(scenario, "live")
    elif source == "live":
        try:
            ce_stages = live_ce_stages(
                scenario, allow_fixture_fallback=requested_mode == "auto"
            )
        except Exception as exc:
            if requested_mode == "live":
                raise RuntimeError(
                    f"live execution failed before fixture fallback: {exc}"
                ) from exc
            resolution = {
                "requested": requested_mode,
                "source": "mock",
                "provider_available": True,
                "message": f"auto live execution failed; using checked-in fixtures: {exc}",
            }
            source = "mock"
            ce_stages = mock_ce_stages(scenario, source)
    else:
        ce_stages = mock_ce_stages(scenario, source)

    stages: list[dict[str, Any]] = []
    if requested_stage in {"ce", "all"}:
        stages.extend(ce_stages)
    if requested_stage in {"pro", "all"}:
        stages.append(pro_stage(scenario, source))

    if any(
        stage["id"] == "corrected-answer" and stage["status"] == "pass"
        for stage in stages
    ):
        final_status = "pass"
    elif stages and all(stage["status"] == "skipped" for stage in stages):
        final_status = "skipped"
    elif any(stage["status"] == "warn" for stage in stages):
        final_status = "warn"
    elif any(
        stage["status"] == "fail" and stage["id"] != "raw-baseline" for stage in stages
    ):
        final_status = "fail"
    else:
        final_status = "pass"

    return {
        "example": EXAMPLE_ID,
        "scenario": name,
        "mode": requested_mode,
        "resolved_mode": source,
        "requested_stage": requested_stage,
        "mode_resolution": resolution,
        "stages": stages,
        "final_status": final_status,
        "summary": "Corrected recommendation passes Community guardrails."
        if final_status == "pass"
        else "Run completed with guardrail warnings or skipped stages.",
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"=== {EXAMPLE_ID}: {report['scenario']} ===",
        f"mode: {report['mode']} -> {report['resolved_mode']}",
        f"stage: {report['requested_stage']}",
        f"preflight: {report['mode_resolution']['message']}",
        "",
    ]
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
        elif stage["id"] == "clips-validation":
            for finding in output.get("findings", []):
                lines.append(f"  - {finding['rule_id']}: {finding['message']}")
        elif stage["id"] == "repair-packet":
            lines.append(f"  repair: {output.get('repair_instructions', '')}")
        elif stage["tier"] == "pro":
            lines.append(f"  evidence: {output.get('explanation', '')}")
        lines.append("")
    lines.append(f"final: {report['final_status']} - {report['summary']}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Progressive common-sense guardrails: Community LLM+CLIPS stages "
            "with optional mock/live Pro Solver and ZEN evidence."
        )
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="car-wash")
    parser.add_argument("--mode", choices=("auto", "live", "mock"), default="auto")
    parser.add_argument("--stage", choices=("ce", "pro", "all"), default="ce")
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
        report = build_report(args.scenario, args.mode, args.stage)
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
