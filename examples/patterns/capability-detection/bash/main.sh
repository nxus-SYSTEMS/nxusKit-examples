#!/usr/bin/env bash
# Capability-Aware Model Selection — Bash CLI Example
#
# Demonstrates: nxuskit-cli models (with filters) + capabilities
# No LLM calls — pure model discovery and capability-based selection.
#
# Usage:
#   bash main.sh [provider]          # Default: ollama
#   bash main.sh ollama --verbose    # Show CLI commands + raw JSON
#   bash main.sh ollama --step       # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"

# Parse provider from positional args, then common flags
PROVIDER="${1:-ollama}"
shift 2>/dev/null || true
parse_args "$@"
check_prereqs

echo "=== Capability-Aware Model Selection Demo ==="
echo
echo "Provider: $PROVIDER"
echo

# --- Step 1: List all models ---
step_pause "Listing models from $PROVIDER..." \
    "nxusKit CLI: models command returns normalized ModelInfo" \
    "Works identically across ollama, openai, claude providers"

models_file="$(tmpfile models.json)"
run_cli models -p "$PROVIDER" -f json -o "$models_file"

model_count=$(jq '.result.models | length' "$models_file")
echo "Available Models: $model_count"
echo
printf "%-40s %s\n" "Model" "Context Window"
printf "%s\n" "$(printf '=%.0s' {1..55})"

jq -r '.result.models[] | "\(.name)\t\(.context_window // "Unknown")"' "$models_file" |
while IFS=$'\t' read -r name ctx; do
    printf "%-40s %s\n" "$name" "$ctx"
done

# --- Step 2: Filter by capabilities ---
step_pause "Filtering models by capabilities..." \
    "nxusKit CLI: --supports flag filters by capability" \
    "--min-context filters by minimum context window size"

echo
echo "Querying models with --min-context 100000..."
large_ctx_file="$(tmpfile large-context.json)"
if run_cli models -p "$PROVIDER" --min-context 100000 -f json -o "$large_ctx_file" 2>/dev/null; then
    large_count=$(jq '.result.models | length' "$large_ctx_file")
    echo "Large Context Models (100K+ tokens): $large_count"
    if [[ "$large_count" -gt 0 ]]; then
        jq -r '.result.models[] | "   [+] \(.name) (\(.context_window // "?") tokens)"' "$large_ctx_file"
    else
        echo "   No models with 100K+ context found."
    fi
else
    echo "   No models with 100K+ context found (or filter not supported for this provider)."
fi

# --- Step 3: Per-model capabilities ---
step_pause "Querying per-model capabilities..." \
    "nxusKit CLI: capabilities command checks specific model features" \
    "Reports vision, streaming, function_calling support"

first_model=$(jq -r '.result.models[0].id // empty' "$models_file")
if [[ -n "$first_model" ]]; then
    echo
    echo "Capabilities for: $first_model"
    caps_file="$(tmpfile caps.json)"
    if run_cli capabilities -p "$PROVIDER" "$first_model" -f json -o "$caps_file" 2>/dev/null; then
        jq '.' "$caps_file"
    else
        echo "   Capabilities query not supported for this provider/model."
    fi
fi

# --- Step 4: Task-based model selection ---
step_pause "Demonstrating task-based model selection..." \
    "Select models based on task requirements" \
    "Filter by context_window for long documents" \
    "Sort by size for fastest inference"

echo
echo "Task-Based Model Selection Examples:"
echo

# Task 1: Large context
echo "Task 1: Process a long document"
best_large=$(jq -r '[.result.models[] | select(.context_window != null)] | sort_by(-.context_window) | .[0] | .name // empty' "$models_file")
best_large_ctx=$(jq -r '[.result.models[] | select(.context_window != null)] | sort_by(-.context_window) | .[0] | .context_window // empty' "$models_file")
if [[ -n "$best_large" ]]; then
    echo "   [+] Recommended: $best_large"
    echo "      Reason: Largest context window ($best_large_ctx tokens)"
else
    echo "   [i] No models with context window info found"
fi

# Task 2: Simple/fast query
echo
echo "Task 2: Simple text generation (small model preferred)"
first=$(jq -r '.result.models[0].name // empty' "$models_file")
if [[ -n "$first" ]]; then
    echo "   [+] Recommended: $first"
    echo "      Reason: First available model"
fi

# Task 3: Most capable
echo
echo "Task 3: Complex analysis task"
if [[ -n "$best_large" ]]; then
    echo "   [+] Recommended: $best_large"
    echo "      Reason: Largest context window ($best_large_ctx tokens)"
fi

# Summary
echo
echo
echo "Model Summary:"
echo "   Total models: $model_count"
ctx_count=$(jq '[.result.models[] | select(.context_window != null)] | length' "$models_file")
echo "   Models with context window info: $ctx_count"

echo
echo "Done."
