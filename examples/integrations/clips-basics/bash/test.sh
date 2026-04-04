#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Use the actual shared rules and data — same as Rust/Go/Python variants
rules_file="$SCRIPT_DIR/../../../shared/rules/animal-classification.clp"
data_file="$SCRIPT_DIR/../../../shared/data/animals.json"

rules_content=$(cat "$rules_file")

# Build fact strings from the first animal in the shared data
facts_array=$(jq -r '[.facts[0:1][] |
    "(animal" +
    " (name \"" + (.values.name // "unknown") + "\")" +
    " (has-backbone " + (.values["has-backbone"].symbol // "unknown") + ")" +
    " (body-temperature " + (.values["body-temperature"].symbol // "unknown") + ")" +
    " (has-fur " + (.values["has-fur"].symbol // "unknown") + ")" +
    " (has-feathers " + (.values["has-feathers"].symbol // "unknown") + ")" +
    " (has-scales " + (.values["has-scales"].symbol // "unknown") + ")" +
    " (lays-eggs " + (.values["lays-eggs"].symbol // "unknown") + ")" +
    " (can-fly " + (.values["can-fly"].symbol // "unknown") + ")" +
    " (lives-in-water " + (.values["lives-in-water"].symbol // "unknown") + ")" +
    ")"
]' "$data_file")

clips_input=$(tmpfile test-clips-input.json)
jq -n --arg rules "$rules_content" --argjson facts "$facts_array" \
    '{rules: $rules, facts: $facts}' > "$clips_input"

out=$(tmpfile test-out.json)
if run_cli clips eval -i "$clips_input" -f json -o "$out" 2>/dev/null; then
    require_jq_key "$out" ".result.fired_rules"

    fired=$(jq '.result.fired_rules // 0' "$out")
    if [[ "$fired" -lt 1 ]]; then
        die "Expected fired_rules >= 1, got $fired"
    fi

    echo "  clips eval (shared rules): PASS (fired_rules=$fired)"
else
    die "clips eval failed with shared animal-classification.clp"
fi
