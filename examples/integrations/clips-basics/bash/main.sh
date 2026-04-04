#!/usr/bin/env bash
# CLIPS Basics — Bash CLI Example
#
# Demonstrates: nxuskit-cli clips eval with shared rule files
# Loads animal-classification rules, asserts facts, displays conclusions.
#
# Usage:
#   bash main.sh                # Run animal classification
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== CLIPS Basics (Animal Classification) Demo ==="
echo

rules_file="$SCRIPT_DIR/../../../shared/rules/animal-classification.clp"
data_file="$SCRIPT_DIR/../../../shared/data/animals.json"

if [[ ! -f "$rules_file" ]]; then
    die "CLIPS rules not found: $rules_file"
fi
if [[ ! -f "$data_file" ]]; then
    die "Animal data not found: $data_file"
fi

# Load rules content
rules_content=$(cat "$rules_file")

# Get animal count
animal_count=$(jq '.facts | length' "$data_file")
echo "Rule base: animal-classification.clp"
echo "Animals to classify: $animal_count"
echo

step_pause "Loading CLIPS rules and animal facts..." \
    "nxusKit CLI: clips eval accepts rules as string + facts array" \
    "Rules define deftemplate + defrule for animal classification" \
    "Facts are asserted from the shared animals.json data"

# Build CLIPS fact strings from the structured JSON data
# Each animal becomes: (animal (name "X") (has-fur yes) (has-feathers no) ...)
facts_array=$(jq -r '[.facts[] |
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

# Construct clips eval input
clips_input="$(tmpfile clips-input.json)"
jq -n --arg rules "$rules_content" --argjson facts "$facts_array" \
    '{rules: $rules, facts: $facts}' > "$clips_input"

step_pause "Running CLIPS evaluation..." \
    "nxusKit CLI: clips eval fires rules against asserted facts" \
    "Classification rules derive animal categories"

out_file="$(tmpfile clips-output.json)"
if ! run_cli clips eval -i "$clips_input" -f json -o "$out_file"; then
    die "CLIPS evaluation failed"
fi

# Display results
fired=$(jq '.result.fired_rules // 0' "$out_file")
matched_count=$(jq '.result.matched_rules | length // 0' "$out_file")
derived_count=$(jq '.result.derived_facts | length // 0' "$out_file")

echo
echo "=== Results ==="
echo "Rules fired: $fired"
echo "Rules matched: $matched_count"
echo "Facts derived: $derived_count"
echo

# Show classifications
step_pause "Displaying classification results..." \
    "derived_facts contain the classification conclusions"

echo "Classifications:"
jq -r '.result.derived_facts[] |
    select(.template == "classification") |
    "  \(.slots.name // "?") → \(.slots.category // "?") (\(.slots.reason // "no reason"))"' \
    "$out_file" 2>/dev/null || \
jq -r '.result.derived_facts[] | "  \(.template // "?"): \(.slots // {} | tostring)"' "$out_file"

echo
echo "Done."
