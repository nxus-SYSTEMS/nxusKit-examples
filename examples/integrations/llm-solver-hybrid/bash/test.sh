#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Test call command
req=$(tmpfile test-req.json)
jq --arg sys "Translate constraints" --arg user "Test constraints" \
    '.messages[0].content = $sys | .messages[1].content = $user' \
    requests/constraint-request.json > "$req"
out=$(tmpfile test-call-out.json)
run_cli call --provider ollama -i "$req" -f json -o "$out"
require_jq_key "$out" ".result"
echo "  call (LLM): PASS"

# Test solver solve with mock_llm_response from shared scenario
solver_out=$(tmpfile test-solver-out.json)
jq '.mock_llm_response' "$SCRIPT_DIR/../scenarios/seating/problem.json" | \
    run_cli solver solve --input - -f json -o "$solver_out" 2>/dev/null

if [[ $? -eq 0 ]]; then
    require_jq_key "$solver_out" ".result.satisfiable"
    sat=$(jq -r '.result.satisfiable' "$solver_out")
    vars=$(jq '.result.assignments | length' "$solver_out")
    if [[ "$sat" != "true" ]]; then
        die "solver solve: expected satisfiable=true, got $sat"
    fi
    echo "  solver solve: PASS (satisfiable=$sat, $vars assignments)"
else
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "  solver solve: PASS (exit 3 — entitlement gate)"
    else
        die "solver solve failed with exit code $rc"
    fi
fi
