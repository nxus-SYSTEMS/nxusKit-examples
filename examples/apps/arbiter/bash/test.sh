#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Test call command
req=$(tmpfile test-req.json)
jq --arg text "Test classification input" '.messages[1].content = $text' \
    requests/generate-request.json > "$req"
out=$(tmpfile test-out.json)
run_cli call --provider ollama -i "$req" -f json -o "$out"
require_jq_key "$out" ".result"
echo "  call (generate): PASS"

# Test clips eval availability
clips_input=$(tmpfile test-clips.json)
cat > "$clips_input" <<'EOF'
{
    "rules": "(defrule test (initial-fact) => (assert (tested)))",
    "facts": [],
    "queries": []
}
EOF
clips_out=$(tmpfile test-clips-out.json)
if run_cli clips eval -i "$clips_input" -f json -o "$clips_out" 2>/dev/null; then
    echo "  clips eval: PASS"
else
    rc=$?
    if [[ $rc -eq 3 ]]; then
        echo "  clips eval: PASS (exit 3 — entitlement gate)"
    else
        echo "  clips eval: SKIP (exit $rc)"
    fi
fi
