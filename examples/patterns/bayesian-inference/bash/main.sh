#!/usr/bin/env bash
# Bayesian Inference — Bash CLI Example
#
# Demonstrates: nxuskit-cli bn infer with multiple inference algorithms
# Compares variable_elimination, junction_tree, loopy_belief_propagation, gibbs.
#
# Usage:
#   bash main.sh                              # Default: haunted-house
#   bash main.sh --scenario coffee-shop       # Use coffee-shop scenario
#   bash main.sh --verbose --step

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

SCENARIO="${SCENARIO:-haunted-house}"
scenario_dir="$SCRIPT_DIR/../scenarios/$SCENARIO"

if [[ ! -d "$scenario_dir" ]]; then
    echo "Available scenarios:"
    ls "$SCRIPT_DIR/../scenarios/"
    die "Scenario not found: $SCENARIO"
fi

network_file="$scenario_dir/network.json"
evidence_file="$scenario_dir/evidence.json"

if [[ ! -f "$network_file" ]]; then
    die "network.json not found in $scenario_dir (BIF-only scenarios need a JSON network file)"
fi

echo "=== Bayesian Inference Demo ==="
echo "Scenario: $SCENARIO"
echo

# Get query nodes from the network (all root/leaf nodes are interesting)
query_nodes=$(jq -r '[.nodes[].name] | join(", ")' "$network_file")
echo "Network nodes: $query_nodes"
echo "Evidence: $(jq -c '.' "$evidence_file")"
echo

# Algorithms to compare
algorithms=("variable_elimination" "junction_tree" "loopy_belief_propagation" "gibbs")
declare -A algo_results

for algo in "${algorithms[@]}"; do
    step_pause "Running $algo inference..." \
        "nxusKit CLI: bn infer with algorithm=$algo" \
        "Each algorithm may produce slightly different results for approximate methods"

    # Construct bn infer input
    input_file="$(tmpfile "bn-input-${algo}.json")"
    jq -n --slurpfile net "$network_file" \
        --slurpfile ev "$evidence_file" \
        --arg algo "$algo" \
        '{network: $net[0], evidence: $ev[0], query_nodes: ($net[0].nodes | map(.name)), algorithm: $algo}' \
        > "$input_file"

    out_file="$(tmpfile "bn-output-${algo}.json")"
    if run_cli bn infer -i "$input_file" -f json -o "$out_file" 2>/dev/null; then
        elapsed=$(jq -r '.result.elapsed_ms // "?"' "$out_file")
        echo "  $algo: completed in ${elapsed}ms"
        algo_results[$algo]="$out_file"
    else
        echo "  $algo: FAILED (exit $?)"
        algo_results[$algo]=""
    fi
done

# Display comparison table
echo
echo "=== Posterior Comparison ==="
echo

# Get first successful result for node list
first_result=""
for algo in "${algorithms[@]}"; do
    if [[ -n "${algo_results[$algo]}" ]]; then
        first_result="${algo_results[$algo]}"
        break
    fi
done

if [[ -z "$first_result" ]]; then
    die "All algorithms failed"
fi

# Print posteriors per query node
nodes=$(jq -r '.result.posteriors | keys[]' "$first_result")
for node in $nodes; do
    echo "--- $node ---"
    printf "  %-30s" ""
    for algo in "${algorithms[@]}"; do
        printf "%-15s" "${algo:0:12}"
    done
    echo

    states=$(jq -r ".result.posteriors.\"$node\" | keys[]" "$first_result")
    for state in $states; do
        printf "  %-30s" "$state"
        for algo in "${algorithms[@]}"; do
            out="${algo_results[$algo]}"
            if [[ -n "$out" ]]; then
                prob=$(jq -r ".result.posteriors.\"$node\".\"$state\" // \"?\"" "$out")
                printf "%-15s" "$(printf '%.4f' "$prob" 2>/dev/null || echo "$prob")"
            else
                printf "%-15s" "N/A"
            fi
        done
        echo
    done
    echo
done

echo "Done."
