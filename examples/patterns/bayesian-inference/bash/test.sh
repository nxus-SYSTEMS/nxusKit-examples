#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

scenario_dir="$SCRIPT_DIR/../scenarios/haunted-house"
input=$(tmpfile test-input.json)
jq -n --slurpfile net "$scenario_dir/network.json" \
    --slurpfile ev "$scenario_dir/evidence.json" \
    '{network: $net[0], evidence: $ev[0], query_nodes: ["ghost", "raccoon"], algorithm: "variable_elimination"}' \
    > "$input"

out=$(tmpfile test-out.json)
run_cli bn infer -i "$input" -f json -o "$out"
require_jq_key "$out" ".result.posteriors"
require_jq_key "$out" ".result.algorithm"

# Semantic: posteriors non-null, algorithm matches
algo=$(jq -r '.result.algorithm' "$out")
if [[ "$algo" != "variable_elimination" ]]; then
    die "Expected algorithm=variable_elimination, got $algo"
fi

posteriors=$(jq '.result.posteriors' "$out")
if [[ "$posteriors" == "null" || "$posteriors" == "{}" ]]; then
    die "Posteriors are null or empty"
fi

echo "  bn infer: PASS (posteriors present, algorithm=variable_elimination)"
