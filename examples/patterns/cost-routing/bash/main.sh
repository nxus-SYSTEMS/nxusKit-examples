#!/usr/bin/env bash
# Model Router (Cost Tiers) — Bash CLI Example
#
# Demonstrates: Task complexity classification + cost-tier routing
# Pure Bash logic — no CLI calls needed (classification is local).
#
# Usage:
#   bash main.sh                # Run with default prompts
#   bash main.sh --verbose      # Show classification details
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== Model Router (Cost Tiers) Demo ==="
echo

# --- Cost tier classification logic ---
# Maps task complexity to model tiers (economy/standard/premium)

classify_task() {
    local prompt="$1"
    local len=${#prompt}
    local word_count
    word_count=$(echo "$prompt" | wc -w | tr -d ' ')

    # Complex keywords that bump up the tier
    local complex_keywords="analyze|compare|trade-off|architecture|design|evaluate|synthesize|critique"

    if [[ $len -gt 200 ]] || echo "$prompt" | grep -qiE "$complex_keywords"; then
        echo "premium"
    elif [[ $len -gt 50 ]] || [[ $word_count -gt 10 ]]; then
        echo "standard"
    else
        echo "economy"
    fi
}

tier_model() {
    case "$1" in
        economy)  echo "qwen3:0.6b" ;;
        standard) echo "qwen3:4b" ;;
        premium)  echo "qwen3:14b" ;;
    esac
}

tier_description() {
    case "$1" in
        economy)  echo "Short, simple queries" ;;
        standard) echo "Medium complexity" ;;
        premium)  echo "Complex analysis" ;;
    esac
}

# --- Step 1: Creating provider context ---
step_pause "Setting up cost router..." \
    "nxusKit: Provider builder pattern with sensible defaults" \
    "Connects to local Ollama instance"

if [[ $VERBOSE -eq 1 ]]; then
    echo "[VERBOSE] Provider: Ollama"
    echo "[VERBOSE] Base URL: http://localhost:11434"
    echo
fi

# --- Step 2: Process prompts ---
step_pause "Processing prompts through cost router..." \
    "Each prompt is analyzed for complexity" \
    "classify_task() determines the appropriate cost tier" \
    "Tier maps to a specific model (economy/standard/premium)"

declare -a prompt_labels=("Simple" "Medium" "Complex")
declare -a prompts=(
    "What is 2+2?"
    "Explain the concept of recursion in programming. Include an example of how it works and when you might use it in practice."
    "Analyze the trade-offs between microservices and monolithic architectures. Compare their scalability, maintainability, deployment complexity, and team coordination requirements."
)

for i in "${!prompts[@]}"; do
    label="${prompt_labels[$i]}"
    prompt="${prompts[$i]}"

    echo "--- $label Prompt ---"
    echo "Input: ${prompt:0:50}..."

    tier=$(classify_task "$prompt")
    model=$(tier_model "$tier")
    echo "Classified as: $tier (would use: $model)"

    if [[ $VERBOSE -eq 1 ]]; then
        echo "[VERBOSE] Prompt length: ${#prompt} chars"
        echo "[VERBOSE] Selected tier: $tier"
        echo "[VERBOSE] Target model: $model"
    fi

    echo
done

# --- Tier summary ---
echo "=== Tier Summary ==="
echo "Economy ($(tier_model economy)): $(tier_description economy)"
echo "Standard ($(tier_model standard)): $(tier_description standard)"
echo "Premium ($(tier_model premium)): $(tier_description premium)"
echo
echo "Done."
