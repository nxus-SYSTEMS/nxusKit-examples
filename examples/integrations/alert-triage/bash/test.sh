#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Test with a single alert from shared data
alert=$(jq '.[0]' "$SCRIPT_DIR/../sample_alerts.json")
req=$(tmpfile test-req.json)
jq --arg alert "$(echo "$alert" | jq -c '.')" \
    '.messages[1].content = $alert' \
    requests/triage-template.json > "$req"

out=$(tmpfile test-out.json)
run_cli call --provider ollama -i "$req" -f json -o "$out"
require_jq_key "$out" ".result.content"

content=$(jq -r '.result.content' "$out")
if [[ -z "$content" || "$content" == "null" ]]; then
    die "Content is null/empty"
fi

echo "  call (triage): PASS (content present, non-null)"
