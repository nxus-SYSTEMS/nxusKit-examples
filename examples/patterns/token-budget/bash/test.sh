#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

req="$(tmpfile request.json)"
jq '.model = "echo"' "$SCRIPT_DIR/requests/story-request.json" > "$req"

out="$(tmpfile stream.jsonl)"
"$NXUSKIT_CLI" call --provider loopback --stream --format jsonl --input "$req" > "$out"

chunk_count=$(jq -rs 'map(select(.type == "chunk")) | length' "$out")
summary_count=$(jq -rs 'map(select(.type == "summary")) | length' "$out")
content=$(jq -rs 'map(select(.type == "summary")) | .[0].content // ""' "$out")

[[ "$chunk_count" -ge 1 ]] || die "Expected at least one JSONL chunk"
[[ "$summary_count" -eq 1 ]] || die "Expected one JSONL summary"
[[ -n "$content" ]] || die "Expected non-empty streamed content"

echo "  call --stream jsonl: PASS ($chunk_count chunk(s), summary present)"
