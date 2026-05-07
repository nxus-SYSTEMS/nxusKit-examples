#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY_MAIN="$ROOT_DIR/python/main.py"
BASH_MAIN="$SCRIPT_DIR/main.sh"
SCENARIOS=(car-wash coupon-stack pallet-door cold-chain)

unset NXUSKIT_PROVIDER NXUSKIT_MODEL ANTHROPIC_API_KEY OPENAI_API_KEY OLLAMA_HOST LMSTUDIO_BASE_URL NXUSKIT_LICENSE_TOKEN ENT_TOKEN_FILE
unset NXUSKIT_COMMON_SENSE_SIMULATE_LIVE

need_jq() {
  command -v jq >/dev/null 2>&1 || {
    echo "jq is required for Bash contract tests" >&2
    exit 2
  }
}

assert_eq() {
  local got="$1" want="$2" label="$3"
  [[ "$got" == "$want" ]] || {
    echo "FAIL $label: got '$got', want '$want'" >&2
    exit 1
  }
}

run_bash_json() {
  bash "$BASH_MAIN" "$@" --json
}

need_jq

bash "$BASH_MAIN" --validate-scenarios >/dev/null

for scenario in "${SCENARIOS[@]}"; do
  out="$(run_bash_json --scenario "$scenario" --mode mock --stage ce)"
  assert_eq "$(jq -r '.scenario' <<<"$out")" "$scenario" "scenario"
  assert_eq "$(jq -r '.resolved_mode' <<<"$out")" "mock" "resolved_mode"
  assert_eq "$(jq -r '.final_status' <<<"$out")" "pass" "final_status"
  assert_eq "$(jq -r '.stages | length' <<<"$out")" "5" "ce stage count"
  assert_eq "$(jq -r '.stages[0].id' <<<"$out")" "raw-baseline" "first stage"
  assert_eq "$(jq -r '.stages[2].id' <<<"$out")" "clips-validation" "clips stage"
  [[ "$(jq -r '.stages[2].output.findings[0].rule_id' <<<"$out")" != "null" ]]

  pro="$(run_bash_json --scenario "$scenario" --mode mock --stage pro)"
  assert_eq "$(jq -r '.stages | length' <<<"$pro")" "1" "pro stage count"
  assert_eq "$(jq -r '.stages[0].tier' <<<"$pro")" "pro" "pro tier"
  assert_eq "$(jq -r '.stages[0].output.entitlement_mode' <<<"$pro")" "mock-fixture" "mock pro entitlement"

  all="$(run_bash_json --scenario "$scenario" --mode mock --stage all)"
  assert_eq "$(jq -r '.stages | length' <<<"$all")" "6" "all stage count"

  py="$(python3 "$PY_MAIN" --scenario "$scenario" --mode mock --stage all --json)"
  assert_eq "$(jq -r '.final_status' <<<"$out")" "$(jq -r '.final_status' <<<"$py")" "python bash status parity"
  assert_eq "$(jq -r '.stages[2].output.findings[0].rule_id' <<<"$all")" "$(jq -r '.stages[2].output.findings[0].rule_id' <<<"$py")" "python bash finding parity"

  export NXUSKIT_COMMON_SENSE_SIMULATE_LIVE=1
  export ENT_TOKEN_FILE="$SCRIPT_DIR/.no-license-token"
  simulated_live="$(run_bash_json --scenario "$scenario" --mode live --stage all)"
  unset NXUSKIT_COMMON_SENSE_SIMULATE_LIVE
  unset ENT_TOKEN_FILE
  assert_eq "$(jq -r '.resolved_mode' <<<"$simulated_live")" "live" "simulated live mode"
  assert_eq "$(jq -r '.final_status' <<<"$simulated_live")" "pass" "simulated live all status"
  assert_eq "$(jq -r '.stages[-1].status' <<<"$simulated_live")" "skipped" "simulated live pro skip"
  assert_eq "$(jq -r '.stages[-1].output.entitlement_mode' <<<"$simulated_live")" "unavailable" "simulated live no entitlement"
done

auto="$(run_bash_json --scenario car-wash --mode auto --stage ce)"
assert_eq "$(jq -r '.resolved_mode' <<<"$auto")" "mock" "auto fallback"
[[ "$(jq -r '.mode_resolution.message' <<<"$auto")" == *"checked-in fixtures"* ]]

set +e
live_err="$(bash "$BASH_MAIN" --scenario car-wash --mode live --stage ce 2>&1 >/dev/null)"
live_rc=$?
set -e
[[ "$live_rc" -ne 0 ]] || {
  echo "FAIL live without provider should fail" >&2
  exit 1
}
[[ "$live_err" == *"live mode requires"* ]] || {
  echo "FAIL live error did not explain provider preflight" >&2
  echo "$live_err" >&2
  exit 1
}

for required in problem.json expected-output.json rules.clp mock-baseline.json mock-facts.json mock-repair.json mock-corrected.json; do
  [[ -f "$ROOT_DIR/scenarios/car-wash/$required" ]] || {
    echo "FAIL missing required fixture $required" >&2
    exit 1
  }
done

tmp_root="$(mktemp -d)"
mkdir -p "$tmp_root/examples/integrations" "$tmp_root/examples/shared/bash"
cp -R "$ROOT_DIR" "$tmp_root/examples/integrations/common-sense-guardrails"
cp "$ROOT_DIR/../../shared/bash/nxuskit-common.sh" "$tmp_root/examples/shared/bash/nxuskit-common.sh"
rm -f "$tmp_root/examples/integrations/common-sense-guardrails/scenarios/car-wash/mock-facts.json"
set +e
missing_msg="$(bash "$tmp_root/examples/integrations/common-sense-guardrails/bash/main.sh" --validate-scenarios 2>&1 >/dev/null)"
missing_rc=$?
set -e
rm -rf "$tmp_root"
[[ "$missing_rc" -ne 0 && "$missing_msg" == *"mock-facts.json"* ]] || {
  echo "FAIL missing artifact validation did not name mock-facts.json" >&2
  echo "$missing_msg" >&2
  exit 1
}

if grep -RE '^[[:space:]]*(import|from)[[:space:]]+(openai|anthropic|ollama)\b' "$PY_MAIN" "$BASH_MAIN" >/dev/null; then
  echo "FAIL direct provider SDK import found" >&2
  exit 1
fi

echo "Bash contract tests passed."
