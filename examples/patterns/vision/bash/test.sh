#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

info="$(tmpfile provider-info.json)"
"$NXUSKIT_CLI" provider info openai --json > "$info"
require_jq_key "$info" ".result.capabilities.vision"

vision=$(jq -r '.result.capabilities.vision' "$info")
[[ "$vision" == "true" ]] || die "Expected OpenAI provider metadata to advertise vision=true"

help_text="$(tmpfile call-help.txt)"
"$NXUSKIT_CLI" call --help > "$help_text"
rg -- '--image-url' "$help_text" >/dev/null || die "call --help missing --image-url"
rg -- '--image-file' "$help_text" >/dev/null || die "call --help missing --image-file"

jq -e '.messages[0].content and .max_tokens' "$SCRIPT_DIR/requests/vision-request.json" >/dev/null

echo "  provider info/call image options: PASS"
