#!/usr/bin/env bash
# Alert Triage — Bash CLI Example
#
# Demonstrates: nxuskit-cli call with structured JSON triage output
# Processes alerts from shared sample_alerts.json, triages each with LLM.
#
# Usage:
#   bash main.sh                # Triage all sample alerts
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== Alert Triage Demo ==="
echo

alerts_file="$SCRIPT_DIR/../sample_alerts.json"
if [[ ! -f "$alerts_file" ]]; then
    die "sample_alerts.json not found: $alerts_file"
fi

alert_count=$(jq 'length' "$alerts_file")
echo "Alerts to triage: $alert_count"
echo

template="$SCRIPT_DIR/requests/triage-template.json"

for idx in $(seq 0 $((alert_count - 1))); do
    alert=$(jq ".[$idx]" "$alerts_file")
    name=$(echo "$alert" | jq -r '.alertname')
    severity=$(echo "$alert" | jq -r '.severity')
    instance=$(echo "$alert" | jq -r '.instance')

    step_pause "Triaging alert $((idx + 1))/$alert_count: $name..." \
        "Severity: $severity, Instance: $instance" \
        "nxusKit CLI: call with triage schema prompt"

    echo "--- Alert $((idx + 1)): $name ($severity) ---"
    echo "  Instance: $instance"
    echo "  Description: $(echo "$alert" | jq -r '.description')"

    # Construct request with alert data
    req_file="$(tmpfile "triage-req-${idx}.json")"
    jq --arg alert "$(echo "$alert" | jq -c '.')" \
        '.messages[1].content = $alert' \
        "$template" > "$req_file"

    out_file="$(tmpfile "triage-out-${idx}.json")"
    if run_cli call --provider ollama -i "$req_file" -f json -o "$out_file"; then
        content=$(jq -r '.result.content' "$out_file")

        if echo "$content" | jq -e '.' &>/dev/null; then
            priority=$(echo "$content" | jq -r '.priority // "?"')
            summary=$(echo "$content" | jq -r '.summary // "N/A"')
            root_cause=$(echo "$content" | jq -r '.root_cause // "N/A"')
            echo "  Triage:"
            echo "    Priority: $priority"
            echo "    Summary: $summary"
            echo "    Root cause: $root_cause"
            actions=$(echo "$content" | jq -r '.suggested_actions // [] | .[]' 2>/dev/null)
            if [[ -n "$actions" ]]; then
                echo "    Actions:"
                echo "$actions" | while read -r action; do
                    echo "      - $action"
                done
            fi
        else
            echo "  Triage: (unstructured) ${content:0:200}"
        fi
    else
        echo "  Triage: FAILED"
    fi
    echo
done

echo "Done."
