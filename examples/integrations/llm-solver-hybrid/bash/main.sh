#!/usr/bin/env bash
# LLM-Solver Hybrid — Bash CLI Example
#
# Demonstrates: LLM translates NL constraints → solver solves (with retry)
# Uses nxuskit-cli call + solver solve with mock_llm_response fallback.
#
# Usage:
#   bash main.sh                            # Default: seating
#   bash main.sh --scenario dungeon         # Use dungeon scenario
#   bash main.sh --verbose --step

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

SCENARIO="${SCENARIO:-seating}"
scenario_dir="$SCRIPT_DIR/../scenarios/$SCENARIO"

if [[ ! -d "$scenario_dir" ]]; then
    echo "Available scenarios:"
    ls "$SCRIPT_DIR/../scenarios/"
    die "Scenario not found: $SCENARIO"
fi

problem_file="$scenario_dir/problem.json"
echo "=== LLM-Solver Hybrid Demo ==="
echo "Scenario: $SCENARIO"
echo "Description: $(jq -r '.description' "$problem_file")"
echo

# --- Step 1: Read NL constraints ---
step_pause "Reading natural language constraints..." \
    "Problem defines constraints in plain English" \
    "LLM translates to solver-compatible JSON"

nl_constraints=$(jq -r '.natural_language_constraints' "$problem_file")
system_prompt=$(jq -r '.system_prompt' "$problem_file")
echo "Constraints:"
echo "$nl_constraints" | head -10
echo

# --- Step 2: LLM translation (with mock fallback) ---
step_pause "Translating constraints via LLM..." \
    "nxusKit CLI: call sends NL constraints to LLM" \
    "Pattern 5: Retry loop on parse failure (max 3 attempts)" \
    "Falls back to mock_llm_response if LLM unavailable"

max_retries=3
solver_input=""
use_mock=0

for attempt in $(seq 1 $max_retries); do
    [[ $VERBOSE -eq 1 ]] && echo "[VERBOSE] Attempt $attempt of $max_retries"

    # Build request
    req_file="$(tmpfile "constraint-req-${attempt}.json")"
    jq --arg sys "$system_prompt" --arg user "$nl_constraints" \
        '.messages[0].content = $sys | .messages[1].content = $user' \
        "$SCRIPT_DIR/requests/constraint-request.json" > "$req_file"

    out_file="$(tmpfile "constraint-out-${attempt}.json")"
    if run_cli call --provider ollama -i "$req_file" -f json -o "$out_file" 2>/dev/null; then
        content=$(jq -r '.result.content' "$out_file")
        # Try to parse as JSON with variables and constraints
        if echo "$content" | jq -e '.variables' &>/dev/null; then
            solver_input="$content"
            echo "LLM successfully translated constraints (attempt $attempt)."
            break
        else
            [[ $VERBOSE -eq 1 ]] && echo "[VERBOSE] LLM response not valid solver JSON, retrying..."
        fi
    else
        [[ $VERBOSE -eq 1 ]] && echo "[VERBOSE] LLM call failed, retrying..."
    fi

    if [[ $attempt -eq $max_retries ]]; then
        echo "LLM translation failed after $max_retries attempts, using mock response."
        use_mock=1
    fi
done

# Fallback to mock
if [[ $use_mock -eq 1 || -z "$solver_input" ]]; then
    solver_input=$(jq '.mock_llm_response' "$problem_file")
    echo "Using mock LLM response from scenario."
fi

echo

# --- Step 3: Solve ---
step_pause "Solving with translated constraints..." \
    "nxusKit CLI: solver solve with LLM-generated variables/constraints" \
    "Pattern 2: File-based request/response"

solver_req="$(tmpfile solver-request.json)"
echo "$solver_input" | jq '.' > "$solver_req"

# Add objective from problem file
objective=$(jq '.objective' "$problem_file")
if [[ "$objective" != "null" ]]; then
    jq --argjson obj "$objective" '. + { objectives: [$obj] }' "$solver_req" > "$(tmpfile solver-req2.json)"
    mv "$(tmpfile solver-req2.json)" "$solver_req"
fi

solver_out="$(tmpfile solver-output.json)"
if ! run_cli solver solve --provider ollama -i "$solver_req" -f json -o "$solver_out" 2>"$(tmpfile error.json)"; then
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
echo "Done."
