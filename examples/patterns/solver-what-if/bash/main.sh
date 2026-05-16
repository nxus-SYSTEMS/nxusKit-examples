#!/usr/bin/env bash
# Solver What-If — Bash CLI Example
#
# Demonstrates: nxuskit-cli solver what-if for single-assumption deltas, with
# a solver solve fallback for multi-assumption scenarios.
#
# Usage:
#   bash main.sh                         # Default: recipe
#   bash main.sh --scenario mars         # Use another scenario
#   bash main.sh --verbose               # Show CLI commands + raw JSON
#   bash main.sh --step                  # Step through with pauses

set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

SCENARIO="${SCENARIO:-recipe}"
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

cli_problem="$(tmpfile "solver-${SCENARIO}-cli-problem.json")"
jq '{
    name,
    description,
    variables: (.variables | map({
        name,
        type: .var_type,
        bounds: [{min: .domain.min}, {max: .domain.max}]
    })),
    constraints: (.constraints | map((.expression // "") | gsub(" = "; " == "))),
    objective: (.objectives[0].direction // "maximize"),
    objective_expr: (.objectives[0].variable // .objectives[0].expression // "")
}' "$problem_file" > "$cli_problem"

echo "=== Solver What-If CLI Demo ==="
echo "Scenario: $SCENARIO"
echo "Problem: $(jq -r '.name // "Unnamed"' "$problem_file")"
echo "Description: $(jq -r '.description // ""' "$problem_file")"
echo
echo "Variables: $(jq '.variables | length' "$problem_file")"
echo "Base constraints: $(jq '.constraints | length' "$problem_file")"
echo "What-if scenarios: $(jq '.what_if_scenarios | length' "$problem_file")"
echo

step_pause "Solving the base problem..." \
    "nxusKit CLI: solver solve establishes the baseline assignment" \
    "The Bash example converts shared ConstraintInput JSON into the CLI expression format"

base_out="$(tmpfile base-output.json)"
set +e
run_cli solver solve -i "$cli_problem" -f json -o "$base_out" 2>"$(tmpfile base-error.json)"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
    if [[ $rc -eq 3 ]]; then
        echo "This example requires a Pro license."
        jq -r '.message // "Entitlement required"' "$(tmpfile base-error.json)" 2>/dev/null || true
        exit 3
    fi
    echo "Solver could not parse this scenario through the CLI expression surface."
    echo "Try --scenario mars or --scenario recipe for v0.9.3 CLI-compatible data."
    exit "$rc"
fi

base_sat=$(jq -r '.result.satisfiable // false' "$base_out")
echo "Base satisfiable: $base_sat"
if [[ "$base_sat" == "true" ]]; then
    echo "Base assignments:"
    jq -r '(.result.assignments // {}) | to_entries[0:8][] | "  \(.key) = \(.value)"' "$base_out"
    remaining=$(jq '((.result.assignments // {}) | length) - 8' "$base_out")
    if [[ "$remaining" -gt 0 ]]; then
        echo "  ... $remaining more"
    fi
fi
echo

what_if_count=$(jq '.what_if_scenarios | length' "$problem_file")
for idx in $(seq 0 $((what_if_count - 1))); do
    name=$(jq -r ".what_if_scenarios[$idx].name" "$problem_file")
    desc=$(jq -r ".what_if_scenarios[$idx].description" "$problem_file")
    mapfile -t assumptions < <(jq -r ".what_if_scenarios[$idx].additional_constraints[] | (.expression // \"\") | gsub(\" = \"; \" == \")" "$problem_file")

    echo "--- What-if: $name ---"
    echo "$desc"
    printf 'Assumptions:\n'
    printf '  - %s\n' "${assumptions[@]}"

    step_pause "Evaluating $name..." \
        "Single assumptions use nxuskit-cli solver what-if --compare" \
        "Multi-assumption scenarios are evaluated by appending constraints and solving"

    out_file="$(tmpfile "what-if-${idx}.json")"
    err_file="$(tmpfile "what-if-${idx}.err")"

    if [[ "${#assumptions[@]}" -eq 1 ]]; then
        if [[ $VERBOSE -eq 1 ]]; then
            echo "[CMD] $NXUSKIT_CLI solver what-if --problem $cli_problem --assume '${assumptions[0]}' --compare --format json"
        fi
        set +e
        "$NXUSKIT_CLI" solver what-if --problem "$cli_problem" --assume "${assumptions[0]}" --compare --format json > "$out_file" 2>"$err_file"
        rc=$?
        set -e
        if [[ $rc -ne 0 ]]; then
            if [[ $rc -eq 3 ]]; then
                echo "  entitlement gate: Pro license required"
                continue
            fi
            echo "  skipped: solver what-if failed for this assumption"
            jq -r '.message // empty' "$err_file" 2>/dev/null || cat "$err_file"
            echo
            continue
        fi

        base_status=$(jq -r '.result.base_result.satisfiable' "$out_file")
        assumed_status=$(jq -r '.result.assumed_result.satisfiable' "$out_file")
        changed=$(jq '.result.diff.variables_changed | length' "$out_file")
        echo "  base satisfiable: $base_status"
        echo "  assumed satisfiable: $assumed_status"
        echo "  changed variables: $changed"
        jq -r '.result.diff.variables_changed[0:6][]? |
            "    \(.name): \(.base_value // "null") -> \(.assumed_value // "null")"' "$out_file"
    else
        assumptions_json="$(tmpfile "assumptions-${idx}.json")"
        printf '%s\n' "${assumptions[@]}" | jq -R . | jq -s . > "$assumptions_json"
        augmented="$(tmpfile "augmented-${idx}.json")"
        jq --slurpfile adds "$assumptions_json" '.constraints += $adds[0]' "$cli_problem" > "$augmented"

        set +e
        run_cli solver solve -i "$augmented" -f json -o "$out_file" 2>"$err_file"
        rc=$?
        set -e
        if [[ $rc -ne 0 ]]; then
            if [[ $rc -eq 3 ]]; then
                echo "  entitlement gate: Pro license required"
                continue
            fi
            echo "  skipped: solver solve failed for this multi-assumption scenario"
            jq -r '.message // empty' "$err_file" 2>/dev/null || cat "$err_file"
            echo
            continue
        fi

        assumed_status=$(jq -r '.result.satisfiable // false' "$out_file")
        echo "  assumed satisfiable: $assumed_status"
        if [[ "$assumed_status" == "true" ]]; then
            jq -n --slurpfile base "$base_out" --slurpfile assumed "$out_file" '
                ($base[0].result.assignments // {}) as $b |
                ($assumed[0].result.assignments // {}) as $a |
                [($b | keys[]) as $k | select($b[$k] != $a[$k]) |
                    {name: $k, base: $b[$k], assumed: $a[$k]}][0:6][] |
                "    \(.name): \(.base) -> \(.assumed)"
            ' -r
        fi
    fi
    echo
done

echo "Done."
