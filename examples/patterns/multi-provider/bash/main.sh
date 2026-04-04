#!/usr/bin/env bash
# Multi-Provider — Bash CLI Example
#
# Demonstrates: Sending the same prompt to multiple LLM providers
# Compares responses, latency, and token usage across providers.
#
# Usage:
#   bash main.sh                # Ollama only (default)
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== Multi-Provider Comparison Demo ==="
echo

# Providers to try — ollama always available, cloud providers optional
providers=("ollama")
# Add cloud providers if API keys are set
[[ -n "${OPENAI_API_KEY:-}" ]] && providers+=("openai")
[[ -n "${ANTHROPIC_API_KEY:-}" ]] && providers+=("claude")

echo "Providers to query: ${providers[*]}"
echo "Prompt: $(jq -r '.messages[0].content' "$SCRIPT_DIR/requests/call-request.json")"
echo

request="$SCRIPT_DIR/requests/call-request.json"
succeeded=0

for provider in "${providers[@]}"; do
    step_pause "Sending prompt to $provider..." \
        "nxusKit CLI: call --provider $provider" \
        "Same request, different provider"

    echo "--- $provider ---"

    out_file="$(tmpfile "response-${provider}.json")"
    if run_cli call --provider "$provider" -i "$request" -f json -o "$out_file" 2>/dev/null; then
        content=$(jq -r '.result.content // "N/A"' "$out_file")
        model=$(jq -r '.result.model // "unknown"' "$out_file")
        elapsed=$(jq -r '.elapsed_ms // "?"' "$out_file")
        input_tok=$(jq -r '.usage.input_tokens // "?"' "$out_file")
        output_tok=$(jq -r '.usage.output_tokens // "?"' "$out_file")

        echo "  Model: $model"
        echo "  Response: ${content:0:200}"
        echo "  Latency: ${elapsed}ms"
        echo "  Tokens: in=$input_tok out=$output_tok"
        ((succeeded++))
    else
        echo "  UNAVAILABLE (exit $?) — check API key or provider availability"
    fi
    echo
done

if [[ $succeeded -eq 0 ]]; then
    die "No providers responded successfully"
fi

# Summary
echo "=== Summary ==="
echo "Providers queried: ${#providers[@]}"
echo "Successful: $succeeded"

echo
echo "Done."
