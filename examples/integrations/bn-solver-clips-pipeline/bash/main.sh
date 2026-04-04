#!/usr/bin/env bash
# BN-Solver-CLIPS Pipeline — Bash CLI Example
#
# Demonstrates: 3-stage pipeline via nxuskit-cli
#   Stage 1: BN inference (bn infer)
#   Stage 2: Constraint solver (solver solve)
#   Stage 3: CLIPS validation (clips eval)
#
# Usage:
#   bash main.sh                            # Default: festival
#   bash main.sh --scenario rescue          # Use rescue scenario
#   bash main.sh --verbose --step

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

SCENARIO="${SCENARIO:-festival}"
scenario_dir="$SCRIPT_DIR/../scenarios/$SCENARIO"

if [[ ! -d "$scenario_dir" ]]; then
    echo "Available scenarios:"
    ls "$SCRIPT_DIR/../scenarios/"
    die "Scenario not found: $SCENARIO"
fi

echo "=== BN-Solver-CLIPS Pipeline Demo ==="
echo "Scenario: $SCENARIO"
echo

# --- Stage 1: Bayesian Network Inference ---
step_pause "Stage 1: Bayesian Network inference..." \
    "nxusKit CLI: bn infer computes posterior distributions" \
    "Evidence from scenario informs probability estimates"

evidence_file="$scenario_dir/evidence.json"
model_file="$scenario_dir/model.bif"

if [[ ! -f "$evidence_file" || ! -f "$model_file" ]]; then
    die "Missing evidence.json or model.bif in $scenario_dir"
fi

# Construct BN request from scenario files
bn_input="$(tmpfile bn-input.json)"
jq -s '{ network: .[0], evidence: .[1] }' "$model_file" "$evidence_file" > "$bn_input" 2>/dev/null || \
    jq --arg model "$(cat "$model_file")" --slurpfile ev "$evidence_file" \
        '{ network_file: $model, evidence: $ev[0] }' <<< '{}' > "$bn_input"

bn_out="$(tmpfile bn-output.json)"
if ! run_cli bn infer -i "$bn_input" -f json -o "$bn_out" 2>"$(tmpfile error.json)"; then
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "This example requires a Pro license."
        exit 3
    fi
    die "BN inference failed with exit code $rc"
fi

echo "BN Posteriors:"
jq '.result.posteriors // {}' "$bn_out"
echo

# --- Stage 2: Constraint Solver ---
step_pause "Stage 2: Constraint solving with BN-informed context..." \
    "nxusKit CLI: solver solve optimizes under constraints" \
    "BN posteriors inform the problem context"

problem_file="$scenario_dir/problem.json"
if [[ ! -f "$problem_file" ]]; then
    die "Missing problem.json in $scenario_dir"
fi

solver_out="$(tmpfile solver-output.json)"
if ! run_cli solver solve --provider ollama -i "$problem_file" -f json -o "$solver_out" 2>"$(tmpfile error.json)"; then
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "This example requires a Pro license."
        exit 3
    fi
    die "Solver failed with exit code $rc"
fi

echo "Solver Result:"
echo "  Satisfiable: $(jq -r '.result.satisfiable // "unknown"' "$solver_out")"
jq -r '(.result.assignments // .result.solution // {}) | to_entries[] | "  \(.key) = \(.value)"' "$solver_out"
echo

# --- Stage 3: CLIPS Validation ---
step_pause "Stage 3: CLIPS rule validation of solver assignments..." \
    "nxusKit CLI: clips eval validates solution against safety rules" \
    "Rules ensure solution meets domain constraints"

rules_file="$scenario_dir/rules.clp"
if [[ -f "$rules_file" ]]; then
    rules_content=$(cat "$rules_file")

    # Build facts from solver solution
    solution_facts=$(jq -r '(.result.assignments // .result.solution // {}) | to_entries | map("(\(.key) \(.value))") | join(" ")' "$solver_out")

    clips_input="$(tmpfile clips-input.json)"
    cat > "$clips_input" <<CLIPS_JSON
{
    "rules": $(jq -Rs '.' <<< "$rules_content"),
    "facts": ["$solution_facts"],
    "queries": []
}
CLIPS_JSON

    clips_out="$(tmpfile clips-output.json)"
    if run_cli clips eval -i "$clips_input" -f json -o "$clips_out" 2>/dev/null; then
        echo "CLIPS Validation:"
        fired=$(jq '.result.fired_rules // 0' "$clips_out")
        echo "  Rules fired: $fired"
        jq -r '(.result.derived_facts // [])[] | "  Fact: \(.template // "unknown") — \(.slots // {})"' "$clips_out" 2>/dev/null || true
    else
        echo "  CLIPS validation unavailable."
    fi
else
    echo "  No CLIPS rules file for this scenario."
fi

echo
echo "Pipeline complete."
echo "Done."
