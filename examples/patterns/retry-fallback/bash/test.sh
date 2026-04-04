#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

out=$(tmpfile test-out.json)
run_cli call --provider ollama -i requests/chat-request.json -f json -o "$out"
require_jq_key "$out" ".result"
echo "  call with fallback: PASS (result present)"
