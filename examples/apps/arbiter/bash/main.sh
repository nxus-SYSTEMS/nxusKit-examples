#!/usr/bin/env bash
# Arbiter — Bash CLI Example
#
# Demonstrates: Auto-retry LLM with CLIPS-driven parameter adjustment
# Loop: call → clips eval → adjust parameters → retry
#
# Usage:
#   bash main.sh                # Run with default config
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== Arbiter (Auto-Retry with CLIPS Validation) Demo ==="
echo

config_file="$SCRIPT_DIR/../shared/solver-config.json"
if [[ ! -f "$config_file" ]]; then
    die "Config not found: $config_file"
fi

# Load config
max_retries=$(jq -r '.max_retries // 3' "$config_file")
confidence_threshold=$(jq -r '.confidence_threshold // 0.7' "$config_file")
conclusion_type=$(jq -r '.conclusion_type // "classification"' "$config_file")

echo "Config: type=$conclusion_type, threshold=$confidence_threshold, max_retries=$max_retries"
echo

# Input text to classify
input_text="The server experienced a sudden spike in memory usage, reaching 95% capacity, which caused the application to become unresponsive for approximately 3 minutes before the auto-scaler provisioned additional instances."

echo "Input: ${input_text:0:80}..."
echo

# Mutable parameters
temperature=0.5
current_max_tokens=200

best_score=0
best_result=""

for attempt in $(seq 1 "$max_retries"); do
    step_pause "Attempt $attempt of $max_retries..." \
        "Temperature: $temperature" \
        "Max tokens: $current_max_tokens" \
        "Confidence threshold: $confidence_threshold"

    echo "--- Attempt $attempt (temp=$temperature) ---"

    # --- Stage 1: Generate LLM response ---
    req_file="$(tmpfile "gen-req-${attempt}.json")"
    jq --arg text "$input_text" --argjson temp "$temperature" --argjson mt "$current_max_tokens" \
        '.messages[1].content = $text | .temperature = $temp | .max_tokens = $mt' \
        "$SCRIPT_DIR/requests/generate-request.json" > "$req_file"

    out_file="$(tmpfile "gen-out-${attempt}.json")"
    if ! run_cli call --provider ollama -i "$req_file" -f json -o "$out_file" 2>/dev/null; then
        echo "  LLM call failed, skipping attempt."
        continue
    fi

    content=$(jq -r '.result.content' "$out_file")

    # Parse classification result
    classification=$(echo "$content" | jq -r '.classification // empty' 2>/dev/null || echo "")
    confidence=$(echo "$content" | jq -r '.confidence // 0' 2>/dev/null || echo "0")
    reasoning=$(echo "$content" | jq -r '.reasoning // empty' 2>/dev/null || echo "")

    if [[ -z "$classification" ]]; then
        echo "  Invalid response format, adjusting parameters."
        # Apply adjustment: bump temperature
        temperature=$(echo "$temperature + 0.2" | bc)
        continue
    fi

    echo "  Classification: $classification"
    echo "  Confidence: $confidence"
    echo "  Reasoning: $reasoning"

    # --- Stage 2: CLIPS evaluation ---
    [[ $VERBOSE -eq 1 ]] && echo "[VERBOSE] Evaluating with CLIPS rules..."

    # Check confidence threshold
    passed=$(echo "$confidence >= $confidence_threshold" | bc -l 2>/dev/null || echo "0")

    if [[ "$passed" -eq 1 ]]; then
        echo "  Status: PASS (confidence >= $confidence_threshold)"
        best_result="$content"
        best_score="$confidence"
        break
    else
        echo "  Status: FAIL (confidence $confidence < $confidence_threshold)"

        # --- Stage 3: Apply adjustment strategy ---
        failure_type="low_confidence"
        adjustment=$(jq -r --arg ft "$failure_type" \
            '.strategies[] | select(.failure_type == $ft) | .adjustments[0].value // 0.2' \
            "$config_file")

        temperature=$(echo "$temperature + $adjustment" | bc)
        echo "  Adjustment: temperature → $temperature"

        # Track best attempt
        if (( $(echo "$confidence > $best_score" | bc -l 2>/dev/null || echo "0") )); then
            best_score="$confidence"
            best_result="$content"
        fi
    fi

    echo
done

# Report final result
echo
echo "=== Final Result ==="
if [[ -n "$best_result" ]]; then
    echo "$best_result" | jq '.'
    echo "Best confidence: $best_score"
else
    echo "No valid classification produced after $max_retries attempts."
fi

echo
echo "Done."
