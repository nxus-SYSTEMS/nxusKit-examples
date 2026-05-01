#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

scenario_dir="$SCRIPT_DIR/../scenarios/recipe"
problem_file="$scenario_dir/problem.json"
cli_problem="$(tmpfile test-cli-problem.json)"

jq '{
    variables: (.variables | map({
        name,
        type: .var_type,
        bounds: [{min: .domain.min}, {max: .domain.max}]
    })),
    constraints: (.constraints | map((.expression // "") | gsub(" = "; " == "))),
    objective: (.objectives[0].direction // "maximize"),
    objective_expr: (.objectives[0].variable // .objectives[0].expression // "")
}' "$problem_file" > "$cli_problem"

assumption=$(jq -r '.what_if_scenarios[] | select(.name == "out_of_eggs") | .additional_constraints[0].expression' "$problem_file")
out="$(tmpfile test-out.json)"
err="$(tmpfile test-err.json)"

if "$NXUSKIT_CLI" solver what-if --problem "$cli_problem" --assume "$assumption" --compare --format json > "$out" 2>"$err"; then
    require_jq_key "$out" ".result.base_result.satisfiable"
    require_jq_key "$out" ".result.assumed_result.satisfiable"
    require_jq_key "$out" ".result.diff.variables_changed"

    base_sat=$(jq -r '.result.base_result.satisfiable' "$out")
    assumed_sat=$(jq -r '.result.assumed_result.satisfiable' "$out")
    changed=$(jq '.result.diff.variables_changed | length' "$out")

    [[ "$base_sat" == "true" ]] || die "Expected base satisfiable=true"
    [[ "$assumed_sat" == "true" ]] || die "Expected assumed satisfiable=true"
    [[ "$changed" -gt 0 ]] || die "Expected at least one changed variable"

    echo "  solver what-if: PASS (base/assumed satisfiable, $changed changed variables)"
else
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "  solver what-if: PASS (exit 3 — entitlement gate working)"
    else
        echo "solver what-if stderr:"
        cat "$err"
        die "solver what-if failed with exit code $rc"
    fi
fi
