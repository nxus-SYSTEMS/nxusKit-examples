#!/usr/bin/env bash
# Structural test for structured-output Bash example
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

req=$(tmpfile test-req.json)
jq --arg entry "Test log entry" '.messages[1].content = $entry' \
    requests/classify-template.json > "$req"

out=$(tmpfile test-out.json)
run_cli call --provider ollama -i "$req" -f json -o "$out"
require_jq_key "$out" ".result"
require_jq_key "$out" ".usage"
require_jq_key "$out" ".trace_id"
echo "  call command: PASS (result, usage, trace_id present)"
