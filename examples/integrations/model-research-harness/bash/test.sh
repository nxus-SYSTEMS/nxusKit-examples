#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/../.tmp/bash-test"

bash "${SCRIPT_DIR}/main.sh" \
  --config "${SCRIPT_DIR}/../configs/nxuskit-harness-basic.yaml" \
  --mode mock \
  --output-dir "$OUT_DIR" \
  --json >/tmp/model-research-harness-bash-test.json

jq -e '.final_status == "pass"' /tmp/model-research-harness-bash-test.json >/dev/null
jq -e '.capability_truth_table[0].harness_validated == true' /tmp/model-research-harness-bash-test.json >/dev/null

bash "${SCRIPT_DIR}/main.sh" \
  --config "${SCRIPT_DIR}/../configs/nxuskit-harness-external-command-fixture.yaml" \
  --mode mock \
  --allow-external \
  --output-dir "$OUT_DIR/external-fixture" \
  --json >/tmp/model-research-harness-external-test.json

jq -e '.final_status == "pass"' /tmp/model-research-harness-external-test.json >/dev/null
jq -e '.results | length == 6' /tmp/model-research-harness-external-test.json >/dev/null
echo "model-research-harness bash smoke: PASS"
