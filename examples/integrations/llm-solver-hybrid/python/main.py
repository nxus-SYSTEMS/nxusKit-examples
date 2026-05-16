#!/usr/bin/env python3
# ruff: noqa: E402
"""LLM-Solver Hybrid Example — nxusKit SDK

Demonstrates natural language -> structured constraints -> solver optimization.
The pipeline supports:
  - Mock mode: use precomputed variables/constraints from problem.json
  - Live mode: call a real LLM provider and parse JSON output with retries

Usage:
  python3 main.py --scenario seating
  python3 main.py --scenario seating --no-mock --provider ollama --model llama3.2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXAMPLES_DIR = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = EXAMPLE_DIR / "scenarios"
MAX_LLM_ATTEMPTS = 3
sys.path.insert(0, str(EXAMPLES_DIR / "shared" / "python"))

from interactive import InteractiveConfig, StepAction
from nxuskit import LLMError, Message, Provider, ResponseFormat
from nxuskit.solver import SolverError, SolverLibraryNotFoundError, SolverSession
from nxuskit.solver_types import SolveResult, SolveStatus, SolverConfig


@dataclass
class JsonPayload:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data


@dataclass
class StageResult:
    name: str
    status: str
    detail: str


def list_scenarios() -> list[str]:
    if not SCENARIOS_DIR.is_dir():
        return []
    return sorted(
        item.name
        for item in SCENARIOS_DIR.iterdir()
        if item.is_dir() and (item / "problem.json").exists()
    )


def load_problem(scenario: str) -> dict:
    path = SCENARIOS_DIR / scenario / "problem.json"
    if not path.exists():
        available = list_scenarios()
        print(f"Error: scenario '{scenario}' not found at {path}")
        if available:
            print(f"Available scenarios: {', '.join(available)}")
        return {}
    with open(path) as handle:
        return json.load(handle)


def create_provider(provider_name: str, model: str, api_key: str | None):
    name = provider_name.lower()
    if name == "claude":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return Provider.claude(model=model, api_key=key)
    if name == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        return Provider.openai(model=model, api_key=key)
    if name == "groq":
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set")
        return Provider.groq(model=model, api_key=key)
    if name == "xai":
        key = api_key or os.environ.get("XAI_API_KEY")
        if not key:
            raise ValueError("XAI_API_KEY not set")
        return Provider.xai(model=model, api_key=key)
    if name == "ollama":
        return Provider.ollama(model=model, api_url="http://localhost:11434")
    if name == "lmstudio":
        return Provider.lmstudio(model=model, api_url="http://localhost:1234/v1")
    raise ValueError(
        "Unknown provider. Supported: claude, openai, groq, xai, ollama, lmstudio"
    )


def extract_json_block(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            body = parts[1]
            if "\n" in body:
                body = body.split("\n", 1)[1]
            return body.strip()
    return text


def parse_llm_response(content: str) -> tuple[list[dict], list[dict]]:
    payload = json.loads(extract_json_block(content))
    variables = payload.get("variables")
    constraints = payload.get("constraints")
    if not isinstance(variables, list) or not isinstance(constraints, list):
        raise ValueError("response must contain 'variables' and 'constraints' arrays")
    if not variables:
        raise ValueError("'variables' array is empty")
    return variables, constraints


def build_constraint_prompt(problem: dict) -> str:
    lines = [
        "Convert the following natural language constraints into structured solver JSON.",
        "Return ONLY a JSON object with 'variables' and 'constraints' arrays.",
        "",
        "Constraints:",
    ]
    for index, item in enumerate(
        problem.get("natural_language_constraints", []), start=1
    ):
        lines.append(f"{index}. {item}")
    return "\n".join(lines)


def extract_variables_live(
    provider,
    problem: dict,
    model: str,
    config: InteractiveConfig,
) -> tuple[list[dict], list[dict], int] | None:
    messages = [
        Message.system(problem.get("system_prompt", "").strip()),
        Message.user(build_constraint_prompt(problem)),
    ]

    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        config.print_request(
            "POST",
            f"https://api.{provider.provider_name}.com/v1/chat",
            {
                "model": model,
                "response_format": ResponseFormat.JSON.value,
                "attempt": attempt,
                "messages": [message.__dict__ for message in messages],
            },
        )

        started = time.time()
        try:
            try:
                response = provider.chat(
                    messages,
                    temperature=0.1,
                    max_tokens=1500,
                    response_format=ResponseFormat.JSON,
                )
            except TypeError:
                response = provider.chat(
                    messages,
                    temperature=0.1,
                    max_tokens=1500,
                )
        except LLMError as exc:
            print(f"  Attempt {attempt}: LLM request failed: {exc}")
            messages.append(
                Message.user("The previous request failed. Reply with valid JSON only.")
            )
            continue

        elapsed_ms = int((time.time() - started) * 1000)
        config.print_response(
            200,
            elapsed_ms,
            {"model": response.model, "content": response.content[:400]},
        )

        try:
            variables, constraints = parse_llm_response(response.content)
            return variables, constraints, attempt
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  Attempt {attempt}: parse failed: {exc}")
            if attempt < MAX_LLM_ATTEMPTS:
                messages.extend(
                    [
                        Message.assistant(response.content),
                        Message.user(
                            "Your previous response could not be parsed. "
                            "Reply with valid JSON only, containing "
                            "'variables' and 'constraints' arrays."
                        ),
                    ]
                )

    return None


def ensure_parameters(constraint: dict) -> dict:
    normalized = dict(constraint)
    normalized["parameters"] = normalized.get("parameters") or {}
    return normalized


def validate_payloads(
    variables: list[dict],
    constraints: list[dict],
) -> tuple[list[dict], list[dict], list[str]]:
    warnings: list[str] = []
    valid_variables: list[dict] = []

    variable_names: set[str] = set()
    for item in variables:
        name = item.get("name")
        has_type = item.get("var_type") is not None
        has_domain = item.get("domain") is not None
        if name and has_type and has_domain:
            valid_variables.append(item)
            variable_names.add(name)
        else:
            label = name or "<unnamed>"
            if not has_type:
                warnings.append(f"Variable '{label}' missing var_type")
            if not has_domain:
                warnings.append(f"Variable '{label}' missing domain")

    valid_constraints: list[dict] = []
    for item in constraints:
        if not isinstance(item, dict):
            warnings.append("Skipping non-object constraint entry")
            continue

        normalized = ensure_parameters(item)
        constraint_name = normalized.get("name", "<unnamed>")
        refs = normalized.get("variables", [])
        if not isinstance(refs, list):
            warnings.append(
                f"Constraint '{constraint_name}' has invalid variables list"
            )
            continue

        unknown = [
            ref for ref in refs if isinstance(ref, str) and ref not in variable_names
        ]
        if unknown:
            warnings.append(
                f"Constraint '{constraint_name}' references unknown variables: "
                f"{', '.join(unknown)}"
            )
            continue

        valid_constraints.append(normalized)

    return valid_variables, valid_constraints, warnings


def solve_status_icon(status: SolveStatus) -> str:
    if status in {SolveStatus.SAT, SolveStatus.OPTIMAL}:
        return "[OK]"
    if status == SolveStatus.UNSAT:
        return "[!!]"
    if status == SolveStatus.TIMEOUT:
        return "[TO]"
    return "[??]"


def wrap_payloads(items: list[dict]) -> list[JsonPayload]:
    return [JsonPayload(item) for item in items]


def solve_problem(
    solver_config: SolverConfig | None,
    variables: list[dict],
    constraints: list[dict],
    objective: dict | None,
    config: InteractiveConfig,
) -> tuple[SolveResult, bool]:
    def run_once(include_objective: bool) -> SolveResult:
        with SolverSession(config=solver_config) as session:
            session.add_variables(wrap_payloads(variables))
            session.add_constraints(wrap_payloads(constraints))
            if include_objective and objective:
                session.set_objective(JsonPayload(objective))
            return session.solve()

    if not objective:
        return run_once(False), False

    try:
        return run_once(True), True
    except (SolverError, RuntimeError) as exc:
        if config.is_verbose():
            print(
                f"[nxusKit] Objective solve failed, retrying without objective: {exc}"
            )
        return run_once(False), False


def format_assignment(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw)


def print_assignments(result: SolveResult) -> None:
    if not result.assignments:
        return
    print("Assignments:")
    for name, value in sorted(result.assignments.items()):
        print(f"  {name} = {format_assignment(value)}")


def interpret_seating(result: SolveResult) -> None:
    tables: dict[int, list[str]] = {}
    for name, value in result.assignments.items():
        if not (name.startswith("guest_") and name.endswith("_table")):
            continue
        guest = name.removeprefix("guest_").removesuffix("_table").replace("_", " ")
        table = int(value.value)
        tables.setdefault(table, []).append(guest.title())

    print("Wedding Seating Arrangement:")
    for table in sorted(tables):
        guests = ", ".join(sorted(tables[table]))
        print(f"  Table {table}: {guests}")


def interpret_dungeon(result: SolveResult) -> None:
    def value(name: str) -> int:
        assignment = result.assignments.get(name)
        return int(assignment.value) if assignment else 0

    treasure_rooms = {value("treasure_room_1"), value("treasure_room_2")}
    boss_room = value("boss_room")
    entry_room = value("entry_room")

    print("Dungeon Layout:")
    for room in range(1, 6):
        labels: list[str] = []
        if room == entry_room:
            labels.append("ENTRY")
        if room == boss_room:
            labels.append("BOSS")
        if room in treasure_rooms:
            labels.append("TREASURE")
        difficulty = value(f"room_{room}_difficulty")
        suffix = f" [{' | '.join(labels)}]" if labels else ""
        print(f"  Room {room}: difficulty={difficulty}{suffix}")


def interpret_road_trip(result: SolveResult) -> None:
    parks = {
        "yosemite": "Yosemite",
        "yellowstone": "Yellowstone",
        "zion": "Zion",
        "glacier": "Glacier",
        "grand_canyon": "Grand Canyon",
    }

    itinerary: list[tuple[int, str, int]] = []
    for key, label in parks.items():
        order = result.assignments.get(f"visit_order_{key}")
        days = result.assignments.get(f"days_at_{key}")
        if order is None or days is None:
            continue
        itinerary.append((int(order.value), label, int(days.value)))

    print("Road Trip Itinerary:")
    for order, label, days in sorted(itinerary):
        print(f"  Stop {order}: {label} ({days} day{'s' if days != 1 else ''})")


def interpret_result(scenario: str, result: SolveResult) -> None:
    if scenario == "seating":
        interpret_seating(result)
    elif scenario == "dungeon":
        interpret_dungeon(result)
    elif scenario == "road-trip":
        interpret_road_trip(result)
    else:
        print_assignments(result)


def main() -> int:
    config = InteractiveConfig.from_args()

    parser = argparse.ArgumentParser(description="LLM-solver hybrid optimization")
    parser.add_argument("--scenario", "-S", default="seating", help="Scenario name")
    parser.add_argument(
        "--mock",
        choices=["true", "false"],
        default=None,
        help="Use mock LLM data (true/false)",
    )
    parser.add_argument(
        "--no-mock",
        action="store_true",
        help="Call a live LLM provider instead of mock data",
    )
    parser.add_argument("--provider", default="ollama", help="LLM provider name")
    parser.add_argument("--model", default="llama3.2", help="Model name")
    parser.add_argument("--api-key", help="Optional provider API key override")
    filtered_args = [
        arg for arg in sys.argv[1:] if arg not in ("--verbose", "-v", "--step", "-s")
    ]
    args = parser.parse_args(filtered_args)

    use_mock = True
    if args.mock is not None:
        use_mock = args.mock == "true"
    if args.no_mock:
        use_mock = False

    problem = load_problem(args.scenario)
    if not problem:
        return 1

    results: list[StageResult] = []
    pipeline_start = time.time()

    print("========================================")
    print(f"  LLM-Solver Hybrid: {args.scenario}")
    print("========================================")
    print()
    print(problem.get("description", ""))
    print()
    print("Pipeline stages:")
    print("  1. Load Problem")
    print("  2. Get Structured Constraints")
    print("  3. Validate")
    print("  4. Solve")
    print("  5. Interpret")
    print("  6. Summary")
    print()
    print(f"Mode: {'MOCK' if use_mock else 'LIVE'}")
    if not use_mock:
        print(f"Provider: {args.provider} ({args.model})")
    print()

    if (
        config.step_pause(
            "Loading problem definition...",
            [
                "Read the natural language constraints and mock response",
                "Live mode can replace the mock response with real LLM output",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Step 1: Load Problem ---")
    print(f"Description: {problem.get('description', '')}")
    nl_constraints = problem.get("natural_language_constraints", [])
    print(f"Natural language constraints: {len(nl_constraints)}")
    for index, item in enumerate(nl_constraints, start=1):
        print(f"  {index}. {item}")
    print()
    results.append(
        StageResult("Load Problem", "[OK]", f"{len(nl_constraints)} constraints loaded")
    )

    if (
        config.step_pause(
            "Getting structured constraints...",
            [
                "Mock mode uses the scenario's precomputed LLM response",
                "Live mode calls the provider with JSON response_format",
                "Live mode falls back to mock data after repeated failures",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Step 2: Get Structured Constraints ---")
    used_mock = use_mock
    llm_attempts = 0

    if use_mock:
        print("(Using mock LLM response from problem.json)")
        variables = list(problem.get("mock_llm_response", {}).get("variables", []))
        constraints = list(problem.get("mock_llm_response", {}).get("constraints", []))
        results.append(
            StageResult(
                "Get Constraints",
                "[OK]",
                f"mock: {len(variables)} variables, {len(constraints)} constraints",
            )
        )
    else:
        try:
            provider = create_provider(args.provider, args.model, args.api_key)
            live_result = extract_variables_live(provider, problem, args.model, config)
        except ValueError as exc:
            print(f"Live provider unavailable: {exc}")
            live_result = None

        if live_result is None:
            print("Falling back to mock response.")
            variables = list(problem.get("mock_llm_response", {}).get("variables", []))
            constraints = list(
                problem.get("mock_llm_response", {}).get("constraints", [])
            )
            used_mock = True
            llm_attempts = MAX_LLM_ATTEMPTS
            results.append(
                StageResult(
                    "Get Constraints",
                    "[FB]",
                    f"fallback to mock: {len(variables)} variables, {len(constraints)} constraints",
                )
            )
        else:
            variables, constraints, llm_attempts = live_result
            results.append(
                StageResult(
                    "Get Constraints",
                    "[OK]",
                    f"live: {len(variables)} variables, {len(constraints)} constraints",
                )
            )

    print(f"Variables parsed: {len(variables)}")
    print(f"Constraints parsed: {len(constraints)}")
    print()

    if (
        config.step_pause(
            "Validating parsed payloads...",
            [
                "Check required variable fields",
                "Verify constraint variable references",
                "Drop malformed constraints before solver execution",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Step 3: Validate ---")
    valid_variables, valid_constraints, warnings = validate_payloads(
        variables, constraints
    )
    print(f"Valid variables:   {len(valid_variables)}/{len(variables)}")
    print(f"Valid constraints: {len(valid_constraints)}/{len(constraints)}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("All checks passed.")
    print()
    results.append(
        StageResult(
            "Validate",
            "[OK]" if not warnings else "[--]",
            f"{len(valid_variables)} vars, {len(valid_constraints)} constraints, {len(warnings)} warnings",
        )
    )

    if (
        config.step_pause(
            "Running solver optimization...",
            [
                "Create a solver session using the scenario solver_config",
                "Add variables and validated constraints",
                "Retry without objective if objective-based solve fails",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Step 4: Solve ---")
    solver_config_data = problem.get("solver_config") or {}
    solver_config = (
        SolverConfig.from_dict(solver_config_data)
        if isinstance(solver_config_data, dict)
        else None
    )
    objective = problem.get("objective")

    try:
        solve_result, objective_applied = solve_problem(
            solver_config,
            valid_variables,
            valid_constraints,
            objective if isinstance(objective, dict) else None,
            config,
        )
    except SolverLibraryNotFoundError as exc:
        print(f"Error: {exc}")
        return 1
    except SolverError as exc:
        print(f"Error: solver failed: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"Error: solver failed: {exc}")
        return 1

    print(f"Status: {solve_result.status.value}")
    print(f"Objective applied: {'yes' if objective_applied else 'no'}")
    if solve_result.objective_value is not None:
        print(f"Objective value: {solve_result.objective_value:.2f}")

    if solve_result.status in {SolveStatus.SAT, SolveStatus.OPTIMAL}:
        print_assignments(solve_result)
    elif solve_result.explanation and solve_result.explanation.unsat_core_labels:
        print("Unsat core:")
        for label in solve_result.explanation.unsat_core_labels:
            print(f"  - {label}")

    if config.is_verbose():
        stats = solve_result.stats
        print(
            "[nxusKit] Solve stats: "
            f"{stats.solve_time_ms}ms, "
            f"{stats.num_variables} vars, "
            f"{stats.num_constraints} constraints"
        )
    print()

    solver_detail = solve_result.status.value
    if solve_result.objective_value is not None:
        solver_detail += f", obj={solve_result.objective_value:.2f}"
    results.append(
        StageResult("Solve", solve_status_icon(solve_result.status), solver_detail)
    )

    if (
        config.step_pause(
            "Interpreting the solution...",
            [
                "Render assignments in scenario-specific terms",
                "Show a human-readable seating plan, dungeon, or itinerary",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Step 5: Interpret ---")
    if solve_result.status in {SolveStatus.SAT, SolveStatus.OPTIMAL}:
        interpret_result(args.scenario, solve_result)
        results.append(
            StageResult(
                "Interpret",
                "[OK]",
                f"scenario={args.scenario}, {len(solve_result.assignments)} assignments",
            )
        )
    else:
        print("No feasible solution to interpret.")
        results.append(StageResult("Interpret", "[--]", "skipped"))
    print()

    print("========================================")
    print("  Pipeline Summary")
    print("========================================")
    print()
    for index, result in enumerate(results, start=1):
        print(f"  {index}. {result.status:>4}  {result.name:<18} {result.detail}")

    total_ms = int((time.time() - pipeline_start) * 1000)
    print()
    print(f"LLM mode:     {'mock' if used_mock else 'live'}")
    if not used_mock:
        print(f"LLM attempts: {llm_attempts}")
    print(f"Total time:   {total_ms}ms")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
