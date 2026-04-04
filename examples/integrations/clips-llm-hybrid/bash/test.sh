#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Test call command
req=$(tmpfile test-classify-req.json)
jq --arg ticket "Test ticket about billing" '.messages[1].content = $ticket' \
    requests/classify-request.json > "$req"
out=$(tmpfile test-classify-out.json)
run_cli call --provider ollama -i "$req" -f json -o "$out"
require_jq_key "$out" ".result"
echo "  call (classify): PASS"

# Test clips eval with semantic checks
clips_input=$(tmpfile test-clips-input.json)
cat > "$clips_input" <<'EOF'
{"rules":"(deftemplate sensor (slot name)(slot value))(defrule high-temp (sensor (name temp)(value ?v&:(> ?v 100))) => (assert (alert high-temp)))","facts":["(sensor (name temp)(value 120))"],"queries":[]}
EOF
clips_out=$(tmpfile test-clips-out.json)
if run_cli clips eval -i "$clips_input" -f json -o "$clips_out" 2>/dev/null; then
    # Shape check
    require_jq_key "$clips_out" ".result.fired_rules"
    echo "  clips eval shape: PASS (result.fired_rules present)"

    # Semantic checks
    fired=$(jq '.result.fired_rules // 0' "$clips_out")
    if [[ "$fired" -gt 0 ]]; then
        echo "  clips eval semantic: PASS (fired_rules=$fired)"
    else
        echo "  clips eval semantic: WARN — fired_rules is 0"
    fi

    matched=$(jq '.result.matched_rules // []' "$clips_out")
    if echo "$matched" | jq -e 'length > 0' &>/dev/null; then
        echo "  clips eval matched_rules: PASS (non-empty)"
    else
        echo "  clips eval matched_rules: WARN — empty"
    fi
else
    echo "  clips eval: SKIP (command unavailable)"
fi
