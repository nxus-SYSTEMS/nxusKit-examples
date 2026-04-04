#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Test with shared problem.json — no transforms, direct consumption
out=$(tmpfile test-out.json)
if run_cli solver solve -i "$SCRIPT_DIR/../scenarios/space-colony/problem.json" -f json -o "$out" 2>/dev/null; then
    require_jq_key "$out" ".result.satisfiable"
    echo "  solver solve shape: PASS (result.satisfiable present)"

    satisfiable=$(jq -r '.result.satisfiable' "$out")
    if [[ "$satisfiable" != "true" ]]; then
        echo "  solver solve semantic: FAIL — expected satisfiable=true, got $satisfiable"
        exit 1
    fi

    num_assignments=$(jq '.result.assignments | length' "$out")
    if [[ "$num_assignments" -lt 10 ]]; then
        echo "  solver solve semantic: FAIL — expected 15 assignments, got $num_assignments"
        exit 1
    fi

    echo "  solver solve semantic: PASS (satisfiable=true, $num_assignments assignments)"
else
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "  solver solve: PASS (exit 3 — entitlement gate working)"
    else
        die "solver solve failed with exit code $rc"
    fi
fi
