#!/usr/bin/env bash
set -euo pipefail
source "../../../shared/bash/nxuskit-common.sh"
parse_args
check_prereqs

# Test generate subcommand (call availability)
req=$(tmpfile test-req.json)
jq --arg desc "Create a simple temperature rule" '.messages[1].content = $desc' \
    requests/generate-request.json > "$req"
out=$(tmpfile test-out.json)
run_cli call --provider ollama -i "$req" -f json -o "$out"
require_jq_key "$out" ".result"
echo "  generate (call): PASS"

# Test validate subcommand with inline CLIPS
clips_file="/tmp/ruler-test-$$.clp"
cat > "$clips_file" <<'EOF'
(deftemplate temperature (slot value))
(defrule hot-alert
    (temperature (value ?t&:(> ?t 30)))
    =>
    (assert (alert hot)))
EOF
output=$(bash main.sh validate "$clips_file" 2>&1)
rm -f "$clips_file"
echo "$output" | grep -q "VALIDATION PASSED" && echo "  validate: PASS"

# Test examples subcommand
examples_output=$(bash main.sh examples 2>&1) || true
echo "$examples_output" | grep -q "Progressive" && echo "  examples: PASS"
