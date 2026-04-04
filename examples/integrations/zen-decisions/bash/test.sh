#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

scenario_dir="$SCRIPT_DIR/../scenarios/maze-rat"
zen_input=$(tmpfile test-zen-input.json)
jq -s '{ table: .[0], input: .[1] }' \
    "$scenario_dir/decision-model.json" "$scenario_dir/input.json" > "$zen_input"

out=$(tmpfile test-out.json)
if run_cli zen eval -i "$zen_input" -f json -o "$out" 2>/dev/null; then
    # Shape checks — all CLI responses wrap payload in .result
    require_jq_key "$out" ".result.output"
    echo "  zen eval shape: PASS (result.output present)"

    # Semantic checks
    output=$(jq '.result.output' "$out")
    if [[ "$output" == "null" ]]; then
        echo "  zen eval semantic: FAIL — output is null (SDK stub?)"
        exit 1
    fi

    rule_count=$(jq '.result.rule_count // 0' "$out")
    if [[ "$rule_count" == "0" ]]; then
        echo "  zen eval semantic: WARN — rule_count is 0"
    fi

    echo "  zen eval semantic: PASS (non-null output, rule_count=$rule_count)"
else
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "  zen eval: PASS (exit 3 — entitlement gate working)"
    else
        die "zen eval failed with exit code $rc"
    fi
fi
