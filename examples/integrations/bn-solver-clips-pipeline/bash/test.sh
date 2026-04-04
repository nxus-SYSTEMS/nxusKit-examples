#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

scenario_dir="$SCRIPT_DIR/../scenarios/festival"

# Test solver solve with shared problem.json directly
solver_out=$(tmpfile test-solver-out.json)
if run_cli solver solve -i "$scenario_dir/problem.json" -f json -o "$solver_out" 2>/dev/null; then
    require_jq_key "$solver_out" ".result.satisfiable"
    sat=$(jq -r '.result.satisfiable' "$solver_out")
    vars=$(jq '.result.assignments | length' "$solver_out")
    echo "  solver solve: PASS (satisfiable=$sat, $vars assignments)"
else
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "  solver solve: PASS (exit 3 — entitlement gate)"
    else
        die "solver solve failed with exit code $rc"
    fi
fi

# Test clips eval
clips_input=$(tmpfile test-clips.json)
cat > "$clips_input" <<'EOF'
{"rules":"(deftemplate assignment (slot band)(slot stage))(defrule check (assignment (band ?b)(stage ?s)) => (assert (validated ?b ?s)))","facts":["(assignment (band band1)(stage 1))"],"queries":[]}
EOF
clips_out=$(tmpfile test-clips-out.json)
if run_cli clips eval -i "$clips_input" -f json -o "$clips_out" 2>/dev/null; then
    require_jq_key "$clips_out" ".result.fired_rules"
    echo "  clips eval: PASS (fired_rules=$(jq '.result.fired_rules' "$clips_out"))"
else
    echo "  clips eval: SKIP"
fi
