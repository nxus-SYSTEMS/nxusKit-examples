#!/usr/bin/env bash
# Constraint Solver — Bash CLI Example
#
# Demonstrates: nxuskit-cli solver solve with shared scenario files
# Multi-step solver lifecycle: satisfaction → optimization → what-if
#
# Usage:
#   bash main.sh                              # Default: space-colony
#   bash main.sh --scenario theme-park        # Use theme-park scenario
#   bash main.sh --verbose                    # Show CLI commands + raw JSON
#   bash main.sh --step                       # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

SCENARIO="${SCENARIO:-space-colony}"
scenario_dir="$SCRIPT_DIR/../scenarios/$SCENARIO"

if [[ ! -d "$scenario_dir" ]]; then
    echo "Available scenarios:"
    ls "$SCRIPT_DIR/../scenarios/"
    die "Scenario not found: $SCENARIO"
fi

problem_file="$scenario_dir/problem.json"
if [[ ! -f "$problem_file" ]]; then
    die "problem.json not found in $scenario_dir"
fi

echo "=== Constraint Solver Demo ==="
echo "Scenario: $SCENARIO"
echo "Problem: $(jq -r '.name // "Unnamed"' "$problem_file")"
echo "Description: $(jq -r '.description // ""' "$problem_file")"
echo

var_count=$(jq '.variables | length' "$problem_file")
constraint_count=$(jq '.constraints | length' "$problem_file")
echo "Variables: $var_count, Constraints: $constraint_count"
echo

# --- Step 1: Satisfaction ---
step_pause "Step 1: Solving for satisfiability..." \
    "nxusKit CLI: solver solve accepts shared problem.json directly" \
    "Library format auto-detected (var_type, constraint_type, parameters)" \
    "Returns variable assignments if a solution exists"

sat_out="$(tmpfile sat-output.json)"
if ! run_cli solver solve -i "$problem_file" -f json -o "$sat_out" 2>"$(tmpfile error.json)"; then
    exit_code=$?
    if [[ $exit_code -eq 3 ]]; then
        echo "This example requires a Pro license."
        jq -r '.message // "Entitlement required"' "$(tmpfile error.json)" 2>/dev/null || true
        exit 3
    fi
    die "Solver failed with exit code $exit_code"
fi

satisfiable=$(jq -r '.result.satisfiable // false' "$sat_out")
echo "Satisfiable: $satisfiable"

if [[ "$satisfiable" == "true" ]]; then
    echo "Solution:"
    jq -r '(.result.assignments // {}) | to_entries[] | "  \(.key) = \(.value)"' "$sat_out"
else
    echo "No solution found — constraints may be infeasible."
fi

# --- Step 2: Objectives ---
step_pause "Step 2: Reviewing optimization objectives..." \
    "nxusKit CLI: solver solve with objectives finds optimal assignments" \
    "Maximizes or minimizes specified variables"

objectives=$(jq '.objectives // []' "$problem_file")
if [[ "$objectives" != "[]" && "$objectives" != "null" ]]; then
    echo
    echo "Objectives:"
    jq -r '.objectives[] | "  \(.direction // "optimize") \(.variable // .expression) (priority: \(.priority // 1))"' "$problem_file"
    echo
    echo "The solution above already includes objective optimization."
fi

# --- Step 3: What-if analysis ---
step_pause "Step 3: What-if analysis..." \
    "Scenario variations defined in problem.json" \
    "Tests alternative conditions without modifying the base problem"

what_if=$(jq '.what_if_scenarios // []' "$problem_file")
if [[ "$what_if" != "[]" && "$what_if" != "null" ]]; then
    what_if_count=$(jq '.what_if_scenarios | length' "$problem_file")
    echo
    echo "What-if scenarios: $what_if_count"
    for idx in $(seq 0 $((what_if_count - 1))); do
        name=$(jq -r ".what_if_scenarios[$idx].name" "$problem_file")
        desc=$(jq -r ".what_if_scenarios[$idx].description" "$problem_file")
        echo
        echo "  [$((idx + 1))] $name"
        echo "      $desc"
    done
fi

echo
echo "Done."
