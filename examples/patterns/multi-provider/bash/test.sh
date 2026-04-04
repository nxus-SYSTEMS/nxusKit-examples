#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

out=$(tmpfile test-out.json)
run_cli call --provider ollama -i requests/call-request.json -f json -o "$out"
require_jq_key "$out" ".result.content"

content=$(jq -r '.result.content' "$out")
if [[ -z "$content" || "$content" == "null" ]]; then
    die "Content is null/empty"
fi

echo "  call (ollama): PASS (content present, non-null)"
