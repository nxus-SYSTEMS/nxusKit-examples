#!/usr/bin/env bash
# Retry-Fallback — Bash CLI Example
#
# Demonstrates: Provider fallback chain with nxuskit-cli call
# Tries each provider in order; returns first success or aggregate error.
#
# Usage:
#   bash main.sh                # Run with default provider chain
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== Retry-Fallback Demo ==="
echo

# Provider fallback chain — tries each in order
providers=("ollama" "openai" "claude")

step_pause "Setting up provider fallback chain..." \
    "nxusKit CLI: call command tries providers sequentially" \
    "First successful response wins" \
    "Chain: ${providers[*]}"

request="$SCRIPT_DIR/requests/chat-request.json"
out_file="$(tmpfile output.json)"

echo "Request: $(jq -r '.messages[0].content' "$request")"
echo
echo "Trying providers: ${providers[*]}"
echo

success=0
for provider in "${providers[@]}"; do
    step_pause "Trying provider: $provider..." \
        "nxusKit CLI: call --provider $provider" \
        "Returns exit 0 on success, non-zero on failure"

    [[ $VERBOSE -eq 1 ]] && echo "[VERBOSE] Trying provider: $provider"

    if run_cli call --provider "$provider" -i "$request" -f json -o "$out_file" 2>/dev/null; then
        echo "Success with provider: $provider"
        echo "Response: $(jq -r '.result.content' "$out_file")"
        echo "Tokens used: $(jq '.usage.total_tokens' "$out_file")"
        success=1
        break
    else
        echo "  Provider $provider: FAILED (exit code $?)"
    fi
done

if [[ $success -eq 0 ]]; then
    die "All providers failed: ${providers[*]}" 1
fi

echo
echo "Done."
