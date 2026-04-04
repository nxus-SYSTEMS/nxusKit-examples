#!/usr/bin/env bash
# Structured Output (JSON Mode) — Bash CLI Example
#
# Demonstrates: nxuskit-cli call with JSON response format + jq parsing
# Classifies log entries into structured {severity, category, summary, actionable}.
#
# Usage:
#   bash main.sh                # Run with default log entries
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== Structured Output (JSON Mode) Demo ==="
echo

# --- Log entries to classify ---
log_entries=(
    "2024-01-15 10:23:45 ERROR Failed login attempt for user admin from IP 192.168.1.100 after 5 retries"
    "2024-01-15 10:24:12 INFO User john.doe successfully authenticated"
    "2024-01-15 10:25:33 CRITICAL Database connection pool exhausted, all connections in use"
)

step_pause "Creating Ollama provider for local development..." \
    "nxusKit CLI: call command with JSON response format" \
    "JSON mode works the same way across all providers" \
    "Ollama uses format parameter, OpenAI uses response_format"

template="$SCRIPT_DIR/requests/classify-template.json"

for i in "${!log_entries[@]}"; do
    entry="${log_entries[$i]}"
    idx=$((i + 1))

    step_pause "Processing log entry $idx..." \
        "nxusKit CLI: call with JSON mode for typed LogClassification" \
        "The schema is enforced by the provider's JSON mode" \
        "Invalid JSON responses are handled gracefully"

    echo "--- Log Entry $idx ---"
    echo "Input: $entry"
    echo

    if [[ $VERBOSE -eq 1 ]]; then
        echo "[VERBOSE] Classifying log entry with JSON mode enabled"
        echo "[VERBOSE] Model: qwen3:4b"
        echo
    fi

    # Build request from template with actual log entry
    req_file="$(tmpfile "classify-request-${idx}.json")"
    jq --arg entry "$entry" \
        '.messages[1].content = $entry' \
        "$template" > "$req_file"

    out_file="$(tmpfile "classify-output-${idx}.json")"

    if run_cli call --provider ollama -i "$req_file" -f json -o "$out_file"; then
        # Extract the LLM response content and parse as JSON
        content=$(jq -r '.result.content' "$out_file")

        # Try to parse the content as JSON
        if echo "$content" | jq -e '.' &>/dev/null; then
            echo "Classification:"
            echo "  Severity:   $(echo "$content" | jq -r '.severity // "unknown"')"
            echo "  Category:   $(echo "$content" | jq -r '.category // "unknown"')"
            echo "  Summary:    $(echo "$content" | jq -r '.summary // "N/A"')"
            echo "  Actionable: $(echo "$content" | jq -r '.actionable // "unknown"')"
        else
            echo "Warning: LLM response was not valid JSON"
            echo "Raw response: $content"
        fi
    else
        echo "Error: Classification failed"
    fi
    echo
done

echo "Done."
