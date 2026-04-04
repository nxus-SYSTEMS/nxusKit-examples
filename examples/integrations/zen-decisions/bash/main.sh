#!/usr/bin/env bash
# ZEN Decision Tables — Bash CLI Example
#
# Demonstrates: nxuskit-cli zen eval with multiple scenario variants
# Evaluates decision tables and compares outcomes across personalities/hit policies.
#
# Usage:
#   bash main.sh                            # Default: maze-rat
#   bash main.sh --scenario potion          # Use potion scenario
#   bash main.sh --verbose --step

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

SCENARIO="${SCENARIO:-maze-rat}"
scenario_dir="$SCRIPT_DIR/../scenarios/$SCENARIO"

if [[ ! -d "$scenario_dir" ]]; then
    echo "Available scenarios:"
    ls "$SCRIPT_DIR/../scenarios/"
    die "Scenario not found: $SCENARIO"
fi

echo "=== ZEN Decision Tables Demo ==="
echo "Scenario: $SCENARIO"
echo

case "$SCENARIO" in
    maze-rat)
        # Multiple personality variants with first-hit policy
        step_pause "Evaluating decision models for 3 personalities..." \
            "nxusKit CLI: zen eval with different decision models" \
            "Comparing cautious, greedy, and explorer personality outcomes"

        input_file="$scenario_dir/input.json"
        for variant in "decision-model" "greedy" "explorer"; do
            model_file="$scenario_dir/${variant}.json"
            [[ -f "$model_file" ]] || continue

            label=$(echo "$variant" | sed 's/decision-model/cautious/')
            echo "--- Personality: $label ---"

            zen_input="$(tmpfile "zen-${variant}-input.json")"
            jq -s '{ table: .[0], input: .[1] }' "$model_file" "$input_file" > "$zen_input"

            out="$(tmpfile "zen-${variant}-output.json")"
            if ! run_cli zen eval -i "$zen_input" -f json -o "$out" 2>"$(tmpfile error.json)"; then
                rc=$?
                if [[ $rc -eq 3 ]]; then
                    echo "This example requires a Pro license."
                    exit 3
                fi
                die "zen eval failed with exit code $rc"
            fi

            echo "Decision: $(jq -r '.result.output // "N/A"' "$out")"
            echo
        done
        ;;

    potion|food-truck)
        # Single model evaluation
        step_pause "Evaluating decision table..." \
            "nxusKit CLI: zen eval with scenario model and input"

        model_file="$scenario_dir/decision-model.json"
        input_file="$scenario_dir/input.json"

        zen_input="$(tmpfile zen-input.json)"
        jq -s '{ table: .[0], input: .[1] }' "$model_file" "$input_file" > "$zen_input"

        out="$(tmpfile zen-output.json)"
        if ! run_cli zen eval -i "$zen_input" -f json -o "$out" 2>"$(tmpfile error.json)"; then
            rc=$?
            if [[ $rc -eq 3 ]]; then
                echo "This example requires a Pro license."
                exit 3
            fi
            die "zen eval failed with exit code $rc"
        fi

        echo "Output:"
        jq '.result.output' "$out"
        ;;

    *)
        die "Unknown scenario: $SCENARIO"
        ;;
esac

echo
echo "Done."
