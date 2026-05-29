#!/usr/bin/env bash
# Gated strict live smoke for the common-sense guardrails walkthrough.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="$SCRIPT_DIR/main.sh"
NXUSKIT_CLI="${NXUSKIT_CLI:-nxuskit-cli}"

if [[ "${RUN_LIVE_SMOKE:-}" != "1" ]]; then
  echo "Set RUN_LIVE_SMOKE=1 to run the strict live smoke." >&2
  exit 2
fi

command -v jq >/dev/null 2>&1 || {
  echo "jq is required for strict live smoke" >&2
  exit 2
}
command -v curl >/dev/null 2>&1 || {
  echo "curl is required for Ollama preflight" >&2
  exit 2
}
command -v "$NXUSKIT_CLI" >/dev/null 2>&1 || {
  echo "nxuskit-cli not found on PATH" >&2
  exit 2
}

cli_version="$("$NXUSKIT_CLI" --version | awk '{print $NF}')"
case "$cli_version" in
  1.*) ;;
  *)
    echo "strict live smoke requires nxuskit-cli 1.x; found $cli_version" >&2
    exit 2
    ;;
esac

export NXUSKIT_PROVIDER="${NXUSKIT_PROVIDER:-ollama}"
export NXUSKIT_MODEL="${NXUSKIT_MODEL:-qwen3.5:4b}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"

curl -sf --max-time 2 "${OLLAMA_HOST%/}/api/tags" >/dev/null || {
  echo "Ollama is not reachable at $OLLAMA_HOST" >&2
  exit 2
}

mkdir -p "$SCRIPT_DIR/.tmp"
out="$SCRIPT_DIR/.tmp/strict-live-car-wash.json"
bash "$MAIN" --scenario car-wash --mode live --stage ce --json > "$out"

jq -e '
  .resolved_mode == "live"
  and .final_status == "pass"
  and ([.stages[] | select(.id as $id | ["raw-baseline", "structured-facts", "corrected-answer"] | index($id)) | .source] | all(. == "live"))
  and (.stages[] | select(.id == "structured-facts") | .status != "fail")
  and any(.stages[] | select(.id == "structured-facts") | .output.objects_required[]?; .object == "car" and .present_at_required_location == false)
  and any(.stages[] | select(.id == "structured-facts") | .output.objects_moved[]?; .object == "person" and .to == "car_wash")
  and any(.stages[] | select(.id == "clips-validation") | .output.findings[]?; .rule_id == "car-required-at-wash" and .status == "fail")
  and (.stages[] | select(.id == "corrected-answer") | .output.content | length > 0)
' "$out" >/dev/null || {
  echo "strict live smoke failed; see $out" >&2
  exit 1
}

echo "strict live smoke passed: $out"
