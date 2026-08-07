#!/usr/bin/env bash
if [[ ${BASH_VERSINFO[0]:-0} -lt 4 ]]; then
  for candidate in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    if [[ -x "$candidate" ]]; then
      exec "$candidate" "$0" "$@"
    fi
  done
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY_MAIN="$ROOT_DIR/python/main.py"
BASH_MAIN="$SCRIPT_DIR/main.sh"
SCENARIOS=(car-wash coupon-stack pallet-door cold-chain)

unset NXUSKIT_PROVIDER NXUSKIT_MODEL ANTHROPIC_API_KEY OPENAI_API_KEY OLLAMA_HOST LMSTUDIO_BASE_URL NXUSKIT_LICENSE_TOKEN ENT_TOKEN_FILE
unset NXUSKIT_COMMON_SENSE_SIMULATE_LIVE NXUSKIT_COMMON_SENSE_FIXTURE_LLM

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
  problem="$ROOT_DIR/scenarios/$scenario/problem.json"
  engine="$(jq -r '.pro_stage.engine // "solver"' "$problem")"
  pro_stage_id="$(jq -r '.pro_stage.id // (if (.pro_stage.engine // "solver") == "zen" then "zen-policy" else "solver-proof" end)' "$problem")"
  bn_enabled="$(jq -r 'if .bn_stage then "true" else "false" end' "$problem")"
  expected_all_selection="clips,$engine"
  expected_all_stage_count="6"
  if [[ "$bn_enabled" == "true" ]]; then
    expected_all_selection="clips,$engine,bn"
    expected_all_stage_count="7"
  fi

  out="$(run_bash_json --scenario "$scenario" --mode mock --stage ce)"
  assert_eq "$(jq -r '.scenario' <<<"$out")" "$scenario" "scenario"
  assert_eq "$(jq -r '.resolved_mode' <<<"$out")" "mock" "resolved_mode"
  assert_eq "$(jq -r '.final_status' <<<"$out")" "pass" "final_status"
  assert_eq "$(jq -r '.stages | length' <<<"$out")" "5" "ce stage count"
  assert_eq "$(jq -r '.stages[0].id' <<<"$out")" "raw-baseline" "first stage"
  assert_eq "$(jq -r '.stages[2].id' <<<"$out")" "clips-validation" "clips stage"
  assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$out")" "clips" "ce guardrail selection"
  [[ "$(jq -r '.stages[2].output.attempts[0].findings[0].rule_id' <<<"$out")" != "null" ]]
  assert_eq "$(jq -r '.stages[2].output.attempts[1].status' <<<"$out")" "pass" "ce repaired attempt"

  pro="$(run_bash_json --scenario "$scenario" --mode mock --stage pro)"
  assert_eq "$(jq -r '.stages | length' <<<"$pro")" "5" "pro loop stage count"
  assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$pro")" "$engine" "pro guardrail selection"
  assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .tier' <<<"$pro")" "pro" "pro tier"
  assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .source' <<<"$pro")" "mock" "mock pro source"
  assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .output.attempts[0].status' <<<"$pro")" "fail" "pro baseline failure"
  assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .output.attempts[1].status' <<<"$pro")" "pass" "pro repaired pass"
  assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .output.attempts[0].findings[0].evidence.runtime_executed' <<<"$pro")" "false" "mock pro runtime label"

  all="$(run_bash_json --scenario "$scenario" --mode mock --stage all)"
  assert_eq "$(jq -r '.stages | length' <<<"$all")" "$expected_all_stage_count" "all stage count"
  assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$all")" "$expected_all_selection" "all guardrail selection"
  if [[ "$bn_enabled" == "true" ]]; then
    assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .tier' <<<"$all")" "community" "auto BN tier"
    assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .output.mechanism' <<<"$all")" "bn" "auto BN mechanism"
    assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .output.attempts[0].status' <<<"$all")" "fail" "auto BN baseline failure"
    assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .output.attempts[1].status' <<<"$all")" "pass" "auto BN repaired pass"
  else
    assert_eq "$(jq -r '[.stages[] | select(.id == "bn-risk")] | length' <<<"$all")" "0" "no BN auto stage"
  fi

  py="$(python3 "$PY_MAIN" --scenario "$scenario" --mode mock --stage all --json)"
  assert_eq "$(jq -r '.final_status' <<<"$out")" "$(jq -r '.final_status' <<<"$py")" "python bash status parity"
  assert_eq "$(jq -r '.stages[2].output.attempts[0].findings[0].rule_id' <<<"$all")" "$(jq -r '.stages[2].output.attempts[0].findings[0].rule_id' <<<"$py")" "python bash finding parity"

  if [[ "$scenario" != "coupon-stack" ]]; then
    export NXUSKIT_COMMON_SENSE_SIMULATE_LIVE=1
    export ENT_TOKEN_FILE="$SCRIPT_DIR/.no-license-token"
    simulated_live="$(run_bash_json --scenario "$scenario" --mode live --stage all)"
    unset NXUSKIT_COMMON_SENSE_SIMULATE_LIVE
    unset ENT_TOKEN_FILE
    assert_eq "$(jq -r '.resolved_mode' <<<"$simulated_live")" "live" "simulated live mode"
    assert_eq "$(jq -r '.final_status' <<<"$simulated_live")" "pass" "simulated live all status"
    assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$simulated_live")" "$expected_all_selection" "simulated live guardrail selection"
    assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .status' <<<"$simulated_live")" "pass" "simulated live pro pass"
    assert_eq "$(jq -r --arg id "$pro_stage_id" '.stages[] | select(.id == $id) | .output.attempts[0].findings[0].evidence.runtime_executed' <<<"$simulated_live")" "false" "simulated live fixture label"
  fi
done

for scenario in coupon-stack cold-chain; do
  problem="$ROOT_DIR/scenarios/$scenario/problem.json"
  engine="$(jq -r '.pro_stage.engine // "solver"' "$problem")"
  pro_stage_id="$(jq -r '.pro_stage.id // (if (.pro_stage.engine // "solver") == "zen" then "zen-policy" else "solver-proof" end)' "$problem")"

  bn="$(run_bash_json --scenario "$scenario" --mode mock --guardrails bn)"
  assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$bn")" "bn" "explicit BN selection"
  assert_eq "$(jq -r '.stages | length' <<<"$bn")" "5" "BN-only stage count"
  assert_eq "$(jq -r '.stages[2].id' <<<"$bn")" "bn-risk" "BN stage id"
  assert_eq "$(jq -r '.stages[2].label' <<<"$bn")" "Bayesian risk / confidence" "BN stage label"
  assert_eq "$(jq -r '.stages[2].tier' <<<"$bn")" "community" "BN stage tier"
  assert_eq "$(jq -r '.stages[2].output.mechanism' <<<"$bn")" "bn" "BN mechanism"
  assert_eq "$(jq -r '.stages[2].output.attempts[0].status' <<<"$bn")" "fail" "BN baseline failure"
  assert_eq "$(jq -r '.stages[2].output.attempts[1].status' <<<"$bn")" "pass" "BN repaired pass"
  assert_eq "$(jq -r '.stages[2].output.attempts[0].findings[0].evidence.runtime_executed' <<<"$bn")" "false" "mock BN runtime label"
  assert_eq "$(jq -r '.stages[] | select(.id == "repair-packet") | .output.findings | map(.mechanism) | join(",")' <<<"$bn")" "bn" "BN repair packet participation"

  clips_bn="$(run_bash_json --scenario "$scenario" --mode mock --guardrails clips,bn)"
  assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$clips_bn")" "clips,bn" "clips BN selection"
  assert_eq "$(jq -r '[.stages[] | select(.id == "clips-validation" or .id == "bn-risk")] | length' <<<"$clips_bn")" "2" "clips BN stages"

  combined="$(run_bash_json --scenario "$scenario" --mode mock --guardrails "clips,$engine,bn")"
  assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$combined")" "clips,$engine,bn" "combined BN selection"
  assert_eq "$(jq -r --arg id "$pro_stage_id" '[.stages[] | select(.id == "clips-validation" or .id == $id or .id == "bn-risk")] | length' <<<"$combined")" "3" "combined guardrail stages"
done

for scenario in car-wash pallet-door; do
  auto_no_bn="$(run_bash_json --scenario "$scenario" --mode mock --guardrails auto)"
  assert_eq "$(jq -r '[.stages[] | select(.id == "bn-risk")] | length' <<<"$auto_no_bn")" "0" "no BN auto for crisp scenario"
  set +e
  bn_err="$(bash "$BASH_MAIN" --scenario "$scenario" --mode mock --guardrails bn --json 2>&1 >/dev/null)"
  bn_rc=$?
  set -e
  [[ "$bn_rc" -ne 0 && "$bn_err" == *"does not support BN"* ]] || {
    echo "FAIL explicit BN should be rejected for $scenario" >&2
    echo "$bn_err" >&2
    exit 1
  }
done

tmp_cli_dir="$(mktemp -d)"
fake_cli="$tmp_cli_dir/nxuskit-cli"
bn_log="$tmp_cli_dir/bn.log"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
sub="${2:-}"
shift 2 || true
input=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input) input="${2:-}"; shift 2 ;;
    -o|--output) output="${2:-}"; shift 2 ;;
    -f|--format) shift 2 ;;
    --quiet) shift ;;
    *) shift ;;
  esac
done

if [[ "$cmd" == "bn" && "$sub" == "infer" ]]; then
  printf 'bn infer\n' >> "$NXUSKIT_FAKE_BN_LOG"
  if jq -e '.evidence.discount_count_bucket == "low" and .evidence.margin_floor_breach == "no" and .evidence.non_stackable_conflict == "no"' "$input" >/dev/null; then
    jq -n '{result:{posteriors:{needs_review:{yes:0.22,no:0.78}}}}' > "$output"
  else
    jq -n '{result:{posteriors:{needs_review:{yes:0.96,no:0.04}}}}' > "$output"
  fi
  exit 0
fi

echo "unexpected command: $cmd $sub" >&2
exit 9
EOF
chmod +x "$fake_cli"
live_bn_baseline="$tmp_cli_dir/baseline-findings.json"
live_bn_corrected="$tmp_cli_dir/corrected-findings.json"
NXUSKIT_CLI="$fake_cli" \
NXUSKIT_FAKE_BN_LOG="$bn_log" \
  "$BASH" -c '
    set -euo pipefail
    cd "$(dirname "$1")"
    source "$1" --scenario car-wash --mode mock --json >/dev/null
    SCENARIO=coupon-stack
    live_bn_findings "$2" "$3" "$4" "$5" "$6"
    live_bn_findings "$2" "$3" "$4" "$7" "$8"
  ' _ \
  "$BASH_MAIN" \
  "$ROOT_DIR/scenarios/coupon-stack/problem.json" \
  "$ROOT_DIR/scenarios/coupon-stack/bn-network.json" \
  "$ROOT_DIR/scenarios/coupon-stack/bn-guardrail.json" \
  "$ROOT_DIR/scenarios/coupon-stack/mock-facts.json" \
  "$live_bn_baseline" \
  "$ROOT_DIR/scenarios/coupon-stack/mock-corrected-facts.json" \
  "$live_bn_corrected"
bn_calls="$(cat "$bn_log")"
assert_eq "$(jq -r '.[0].status' "$live_bn_baseline")" "fail" \
  "direct coupon BN baseline status"
assert_eq "$(jq -r '.[0].status' "$live_bn_corrected")" "pass" \
  "direct coupon BN repaired status"
assert_eq "$(jq -r '.[0].evidence.runtime_executed' "$live_bn_baseline")" \
  "true" "direct coupon BN runtime label"
assert_eq "$(grep -c '^bn infer$' <<<"$bn_calls")" "2" \
  "direct coupon BN CLI call count"
rm -rf "$tmp_cli_dir"

tmp_cli_dir="$(mktemp -d)"
fake_cli="$tmp_cli_dir/nxuskit-cli"
clips_log="$tmp_cli_dir/clips.log"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
sub="${2:-}"
shift 2 || true
input=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input) input="${2:-}"; shift 2 ;;
    -o|--output) output="${2:-}"; shift 2 ;;
    -f|--format) shift 2 ;;
    --quiet) shift ;;
    *) shift ;;
  esac
done

if [[ "$cmd" != "clips" || "$sub" != "eval" ]]; then
  echo "unexpected command: $cmd $sub" >&2
  exit 9
fi

fact="$(jq -r '.facts[0]' "$input")"
printf '%s\n' "$fact" >> "$NXUSKIT_FAKE_CLIPS_LOG"
if [[ "$fact" == *"(non-stackable-count 2)"* ]]; then
  jq -n '{result:{derived_facts:[{template:"guardrail-finding",slots:{"rule-id":"non-stackable-discount-conflict",status:"fail",severity:"error",message:"The recommendation combines non-stackable promotion families."}}]}}' > "$output"
elif [[ "$fact" == *"(non-stackable-count 1)"* ]]; then
  jq -n '{result:{derived_facts:[]}}' > "$output"
else
  echo "coupon-stack CLIPS fact did not contain the derived non-stackable count: $fact" >&2
  exit 9
fi
EOF
chmod +x "$fake_cli"
live_clips_baseline="$tmp_cli_dir/baseline-findings.json"
live_clips_corrected="$tmp_cli_dir/corrected-findings.json"
NXUSKIT_CLI="$fake_cli" \
NXUSKIT_FAKE_CLIPS_LOG="$clips_log" \
  "$BASH" -c '
    set -euo pipefail
    cd "$(dirname "$1")"
    source "$1" --scenario car-wash --mode mock --json >/dev/null
    SCENARIO=coupon-stack
    live_clips_eval "$2" "$3" "$4"
    live_clips_eval "$2" "$5" "$6"
  ' _ \
  "$BASH_MAIN" \
  "$ROOT_DIR/scenarios/coupon-stack" \
  "$ROOT_DIR/scenarios/coupon-stack/mock-facts.json" \
  "$live_clips_baseline" \
  "$ROOT_DIR/scenarios/coupon-stack/mock-corrected-facts.json" \
  "$live_clips_corrected"
clips_calls="$(cat "$clips_log")"
assert_eq "$(jq -r '.[0].rule_id' "$live_clips_baseline")" \
  "non-stackable-discount-conflict" \
  "direct coupon CLIPS derived policy finding"
assert_eq "$(jq -r '.[0].status' "$live_clips_corrected")" "pass" \
  "direct coupon CLIPS repaired status"
assert_eq "$(grep -c '(non-stackable-count 2)' <<<"$clips_calls")" "1" \
  "direct coupon CLIPS baseline count"
assert_eq "$(grep -c '(non-stackable-count 1)' <<<"$clips_calls")" "1" \
  "direct coupon CLIPS repaired count"
rm -rf "$tmp_cli_dir"

coupon_parity_tmp="$(mktemp -d)"
cleanup_coupon_parity_tmp() {
  rm -rf "$coupon_parity_tmp"
}
trap cleanup_coupon_parity_tmp EXIT
coupon_parity_repo="$coupon_parity_tmp/repo"
coupon_parity_root="$coupon_parity_repo/examples/integrations/common-sense-guardrails"
mkdir -p "$coupon_parity_repo/examples/integrations" "$coupon_parity_repo/examples/shared"
cp -R "$ROOT_DIR" "$coupon_parity_root"
cp -R "$ROOT_DIR/../../shared/bash" "$coupon_parity_repo/examples/shared/bash"
coupon_parity_log="$coupon_parity_tmp/clips.log"

assert_coupon_count_parity() {
  local label="$1"
  local baseline_discounts="$2"
  local baseline_resources="$3"
  local corrected_discounts="$4"
  local corrected_resources="$5"
  local expected_baseline="$6"
  local expected_corrected="$7"
  local counts output

  jq --argjson discounts "$baseline_discounts" --argjson resources "$baseline_resources" \
    '.candidate_actions[0].discounts = $discounts | .resources = $resources' \
    "$ROOT_DIR/scenarios/coupon-stack/mock-facts.json" \
    > "$coupon_parity_root/scenarios/coupon-stack/mock-facts.json"
  jq --argjson discounts "$corrected_discounts" --argjson resources "$corrected_resources" \
    '.candidate_actions[0].discounts = $discounts | .resources = $resources' \
    "$ROOT_DIR/scenarios/coupon-stack/mock-corrected-facts.json" \
    > "$coupon_parity_root/scenarios/coupon-stack/mock-corrected-facts.json"
  "$BASH" -c '
    set -euo pipefail
    cd "$(dirname "$1")"
    source "$1" --scenario car-wash --mode mock --json >/dev/null
    SCENARIO=coupon-stack
    clips_facts_json "$2"
    clips_facts_json "$3"
  ' _ \
    "$coupon_parity_root/bash/main.sh" \
    "$coupon_parity_root/scenarios/coupon-stack/mock-facts.json" \
    "$coupon_parity_root/scenarios/coupon-stack/mock-corrected-facts.json" \
    > "$coupon_parity_log"
  output="$(
    bash "$coupon_parity_root/bash/main.sh" \
      --scenario coupon-stack --mode mock --guardrails clips --json
  )"
  assert_eq "$(jq -r '.final_status' <<<"$output")" "pass" "$label final status"
  counts="$(sed -n 's/.*(non-stackable-count \([0-9][0-9]*\)).*/\1/p' "$coupon_parity_log")"
  assert_eq "$(sed -n '1p' <<<"$counts")" "$expected_baseline" "$label baseline count"
  assert_eq "$(sed -n '2p' <<<"$counts")" "$expected_corrected" "$label corrected count"
}

assert_coupon_count_parity \
  "missing resource is conservatively non-stackable" \
  '["missing-a", "missing-b"]' '[{"id":"other","type":"coupon","stackable":true}]' \
  '["missing-a"]' '[{"id":"other","type":"coupon","stackable":true}]' \
  "2" "1"
assert_coupon_count_parity \
  "duplicate resource uses the last row" \
  '["repeat"]' '[{"id":"repeat","stackable":false},{"id":"repeat","stackable":true}]' \
  '["repeat"]' '[{"id":"repeat","stackable":true},{"id":"repeat","stackable":false}]' \
  "0" "1"
assert_coupon_count_parity \
  "duplicate selected discounts count per occurrence" \
  '["repeat", "repeat"]' '[{"id":"repeat","stackable":true},{"id":"repeat","stackable":false}]' \
  '["repeat"]' '[{"id":"repeat","stackable":true},{"id":"repeat","stackable":false}]' \
  "2" "1"
assert_coupon_count_parity \
  "empty selected discounts use policy context fallback" \
  '[]' '[{"id":"welcome-25","type":"coupon","stackable":false}]' \
  '[]' '[{"id":"welcome-25","type":"coupon","stackable":false}]' \
  "0" "1"

cleanup_coupon_parity_tmp
trap - EXIT

coupon_validation_tmp="$(mktemp -d)"
cleanup_coupon_validation_tmp() {
  rm -rf "$coupon_validation_tmp"
}
trap cleanup_coupon_validation_tmp EXIT
coupon_validation_facts="$coupon_validation_tmp/facts.json"

coupon_invalid_cases=(
  'boolean resource id|.resources[0].id = true'
  'number resource id|.resources[0].id = 1'
  'array resource id|.resources[0].id = []'
  'object resource id|.resources[0].id = {}'
  'null resource id|.resources[0].id = null'
  'missing resource stackable|del(.resources[0].stackable)'
  'nonboolean resource stackable|.resources[0].stackable = "false"'
  'missing resource type|del(.resources[0].type)'
  'nonstring resource type|.resources[0].type = 1'
  'empty resources|.resources = []'
  'empty selected discount id|.candidate_actions[0].discounts = [""]'
)
coupon_validation_failures=0
for invalid_case in "${coupon_invalid_cases[@]}"; do
  label="${invalid_case%%|*}"
  mutation="${invalid_case#*|}"
  jq "$mutation" "$ROOT_DIR/scenarios/coupon-stack/mock-facts.json" \
    > "$coupon_validation_facts"
  if "$BASH" -c '
    set -euo pipefail
    cd "$(dirname "$1")"
    source "$1" --scenario car-wash --mode mock --json >/dev/null
    SCENARIO=coupon-stack
    facts_json_valid < "$2"
  ' _ "$BASH_MAIN" "$coupon_validation_facts"; then
    echo "FAIL coupon fact validator accepted $label" >&2
    coupon_validation_failures=$((coupon_validation_failures + 1))
  fi
done
if [[ "$coupon_validation_failures" -ne 0 ]]; then
  echo "FAIL coupon fact validator accepted $coupon_validation_failures malformed typed-resource case(s)" >&2
  exit 1
fi
cleanup_coupon_validation_tmp
trap - EXIT

coupon_containment_tmp="$(mktemp -d)"
coupon_containment_cli="$coupon_containment_tmp/nxuskit-cli"
coupon_contact_sentinel="$coupon_containment_tmp/provider-contacted"
cat > "$coupon_containment_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'provider command reached\n' >> "$NXUSKIT_COUPON_CONTACT_SENTINEL"
exit 97
EOF
chmod +x "$coupon_containment_cli"

set +e
coupon_auto="$({
  NXUSKIT_CLI="$coupon_containment_cli" \
  NXUSKIT_COUPON_CONTACT_SENTINEL="$coupon_contact_sentinel" \
  NXUSKIT_PROVIDER=literal-coupon-provider-canary \
  NXUSKIT_MODEL=literal-coupon-model-canary \
  bash "$BASH_MAIN" --scenario coupon-stack --mode auto \
    --guardrails clips,bn --json
} 2>"$coupon_containment_tmp/auto.err")"
coupon_auto_rc=$?
set -e
coupon_auto_contacted=false
[[ -e "$coupon_contact_sentinel" ]] && coupon_auto_contacted=true
rm -f "$coupon_contact_sentinel"

set +e
coupon_live_err="$({
  NXUSKIT_CLI="$coupon_containment_cli" \
  NXUSKIT_COUPON_CONTACT_SENTINEL="$coupon_contact_sentinel" \
  NXUSKIT_PROVIDER=literal-coupon-provider-canary \
  NXUSKIT_MODEL=literal-coupon-model-canary \
  bash "$BASH_MAIN" --scenario coupon-stack --mode live \
    --guardrails clips,bn --json
} 2>&1 >/dev/null)"
coupon_live_rc=$?
set -e
coupon_live_contacted=false
[[ -e "$coupon_contact_sentinel" ]] && coupon_live_contacted=true

[[ "$coupon_auto_contacted" == false ]] || {
  echo "FAIL coupon auto contacted the provider/CLI before containment (exit $coupon_auto_rc)" >&2
  rm -rf "$coupon_containment_tmp"
  exit 1
}
assert_eq "$(jq -r '.resolved_mode' <<<"$coupon_auto")" "mock" \
  "coupon auto containment source"
assert_eq "$(jq -r '.mode_resolution.provider_contacted' <<<"$coupon_auto")" \
  "false" "coupon auto no provider contact"
[[ "$coupon_live_contacted" == false ]] || {
  echo "FAIL coupon live contacted the provider/CLI before containment" >&2
  rm -rf "$coupon_containment_tmp"
  exit 1
}
assert_eq "$coupon_live_rc" "2" "coupon live containment exit"
[[ "$coupon_live_err" == \
  "ERROR: coupon_live_strict_schema_transport_unavailable_v1_0_5:"* ]] || {
  echo "FAIL coupon live containment error: $coupon_live_err" >&2
  rm -rf "$coupon_containment_tmp"
  exit 1
}
rm -rf "$coupon_containment_tmp"

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

set +e
default_live_err="$(bash "$BASH_MAIN" --scenario car-wash --stage ce 2>&1 >/dev/null)"
default_live_rc=$?
set -e
[[ "$default_live_rc" -ne 0 ]] || {
  echo "FAIL default mode should be live and fail without provider" >&2
  exit 1
}
[[ "$default_live_err" == *"live mode requires"* ]] || {
  echo "FAIL default live error did not explain provider preflight" >&2
  echo "$default_live_err" >&2
  exit 1
}

tmp_cli_dir="$(mktemp -d)"
fake_cli="$tmp_cli_dir/nxuskit-cli"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
shift || true
input=""
output=""
model=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input) input="${2:-}"; shift 2 ;;
    -o|--output) output="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

assert_call_controls() {
  local expected_format="$1"
  jq -e '.thinking_mode == "disabled"' "$input" >/dev/null || {
    echo "missing thinking_mode disabled in $input" >&2
    exit 9
  }
  jq -e --arg expected "$expected_format" '.response_format.type == $expected' "$input" >/dev/null || {
    echo "unexpected response_format in $input" >&2
    exit 9
  }
  if [[ "$expected_format" == "json_schema" ]]; then
    jq -e '.response_format.schema.required | index("objects_required")' "$input" >/dev/null || {
      echo "facts response schema missing required fields" >&2
      exit 9
    }
  fi
}

if [[ "$cmd" == "clips" ]]; then
  printf '{}\n' > "$output"
  exit 0
fi

prompt="$(jq -r '.messages[-1].content // empty' "$input")"
if [[ "$prompt" == *"Return only JSON"* || "$prompt" == *"previous extraction was invalid"* ]]; then
  assert_call_controls json_schema
  if [[ "$model" != "qwen3:4b" ]]; then
    echo "expected facts model qwen3:4b, got ${model:-<unset>}" >&2
    exit 9
  fi
  content='Here are the extracted JSON facts:

```json
{
  "goal": {"object": "car", "outcome": "wash", "target_location": "car_wash"},
  "candidate_actions": [
    {
      "id": "walk-to-car-wash",
      "moves": ["person"],
      "recommendation": "walk",
      "target_location": "car_wash"
    }
  ],
  "objects_required": [
    {
      "current_location": "home",
      "object": "car",
      "present_at_required_location": false,
      "required_location": "car_wash"
    }
  ],
  "objects_moved": [
    {
      "action_id": "walk-to-car-wash",
      "from": "home",
      "object": "person",
      "to": "car_wash"
    }
  ],
  "resources": [{"id": "car", "state": "at_home", "type": "vehicle"}],
  "constraints": [{"id": "car-must-be-at-wash", "type": "physical"}],
  "policy_context": {"distance_meters": 50, "domain": "physical_planning"},
  "confidence": 0.8
}
```

Trailing prose.'
elif [[ "$prompt" == *"failed these feasibility checks"* || "$prompt" == *"washing the car requires"* ]]; then
  assert_call_controls text
  if [[ "$model" != "gemma3" ]]; then
    echo "expected repair model gemma3, got ${model:-<unset>}" >&2
    exit 9
  fi
  content="Drive the car to the car wash, or walk only if the car is already there."
else
  assert_call_controls text
  if [[ "$model" != "llama3.2" ]]; then
    echo "expected baseline model llama3.2, got ${model:-<unset>}" >&2
    exit 9
  fi
  content="Walk to the car wash because it is nearby."
fi
jq -n --arg content "$content" '{result:{content:$content}}' > "$output"
EOF
chmod +x "$fake_cli"
wrapped_live="$(
  NXUSKIT_CLI="$fake_cli" \
  NXUSKIT_PROVIDER=ollama \
  NXUSKIT_MODEL=llama3.2 \
  NXUSKIT_COMMON_SENSE_FACTS_MODEL=qwen3:4b \
  NXUSKIT_COMMON_SENSE_REPAIR_MODEL=gemma3 \
  bash "$BASH_MAIN" --scenario car-wash --mode live --stage ce --json
)"
rm -rf "$tmp_cli_dir"
assert_eq "$(jq -r '.resolved_mode' <<<"$wrapped_live")" "live" "wrapped JSON live mode"
assert_eq "$(jq -r '.stages[] | select(.id == "structured-facts") | .source' <<<"$wrapped_live")" "live" "wrapped JSON source"
assert_eq "$(jq -r '.stages[] | select(.id == "structured-facts") | .status' <<<"$wrapped_live")" "warn" "wrapped JSON warning"
[[ "$(jq -r '.stages[] | select(.id == "structured-facts") | .message' <<<"$wrapped_live")" == *"wrapped JSON in prose"* ]] || {
  echo "FAIL wrapped JSON extraction did not emit warning" >&2
  echo "$wrapped_live" >&2
  exit 1
}

tmp_cli_dir="$(mktemp -d)"
fake_cli="$tmp_cli_dir/nxuskit-cli"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
shift || true
input=""
output=""
model=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input) input="${2:-}"; shift 2 ;;
    -o|--output) output="${2:-}"; shift 2 ;;
    --model) model="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ "$cmd" == "clips" ]]; then
  printf '{}\n' > "$output"
  exit 0
fi

if [[ "$cmd" == "call" && "$model" != "llama3:8b" ]]; then
  echo "expected model llama3:8b, got ${model:-<unset>}" >&2
  exit 9
fi

assert_call_controls() {
  local expected_format="$1"
  jq -e '.thinking_mode == "disabled"' "$input" >/dev/null || {
    echo "missing thinking_mode disabled in $input" >&2
    exit 9
  }
  jq -e --arg expected "$expected_format" '.response_format.type == $expected' "$input" >/dev/null || {
    echo "unexpected response_format in $input" >&2
    exit 9
  }
}

prompt="$(jq -r '.messages[-1].content // empty' "$input")"
if [[ "$prompt" == *"Return only JSON"* || "$prompt" == *"previous extraction was invalid"* ]]; then
  assert_call_controls json_schema
  content='{
    "goal": "Get a car washed",
    "candidate_actions": [{"name": "Walk or jog"}],
    "objects_required": {"location1": ["car"], "location2": []},
    "objects_moved": {"location1": ["car"], "location2": []},
    "resources": {"energy": "walking"},
    "constraints": [{"type": "distance", "value": "50 meters"}],
    "policy_context": "car wash",
    "confidence": 0.8
  }'
elif [[ "$prompt" == *"failed these feasibility checks"* || "$prompt" == *"washing the car requires"* ]]; then
  assert_call_controls text
  content="Drive the car to the car wash, or walk only if the car is already there."
else
  assert_call_controls text
  content="Walk to the car wash because it is nearby."
fi
jq -n --arg content "$content" '{result:{content:$content}}' > "$output"
EOF
chmod +x "$fake_cli"
malformed_live="$(
  NXUSKIT_CLI="$fake_cli" \
  NXUSKIT_PROVIDER=ollama \
  NXUSKIT_MODEL=llama3:8b \
  bash "$BASH_MAIN" --scenario car-wash --mode live --stage ce --json
)"
rm -rf "$tmp_cli_dir"
assert_eq "$(jq -r '.resolved_mode' <<<"$malformed_live")" "live" "malformed facts live mode"
assert_eq "$(jq -r '.final_status' <<<"$malformed_live")" "fail" "malformed facts final status"
assert_eq "$(jq -r '.stages[] | select(.id == "structured-facts") | .source' <<<"$malformed_live")" "mock" "malformed facts fallback source"
assert_eq "$(jq -r '.stages[] | select(.id == "structured-facts") | .status' <<<"$malformed_live")" "fail" "malformed facts fallback status"
[[ "$(jq -r '.stages[] | select(.id == "structured-facts") | .message' <<<"$malformed_live")" == *"using checked-in fact fixture"* ]] || {
  echo "FAIL malformed fact extraction did not fall back to fixture" >&2
  echo "$malformed_live" >&2
  exit 1
}

tmp_cli_dir="$(mktemp -d)"
fake_cli="$tmp_cli_dir/nxuskit-cli"
solver_log="$tmp_cli_dir/solver.log"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
sub="${2:-}"
if [[ "$cmd" == "call" ]]; then
  sub=""
else
  shift || true
fi
shift || true
input=""
output=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input) input="${2:-}"; shift 2 ;;
    -o|--output) output="${2:-}"; shift 2 ;;
    -f|--format|--model|--provider) shift 2 ;;
    --quiet) shift ;;
    *) shift ;;
  esac
done

if [[ "$cmd" == "solver" && "$sub" == "solve" ]]; then
  printf 'solver solve\n' >> "$NXUSKIT_FAKE_SOLVER_LOG"
  jq -e '.variables[] | select(.name == "required_object_present_after_action")' "$input" >/dev/null
  actual="$(jq -r '.variables[] | select(.name == "required_object_present_after_action") | .domain.min' "$input")"
  if [[ "$actual" == "1" ]]; then
    jq -n '{result:{satisfiable:true}}' > "$output"
  else
    jq -n '{result:{satisfiable:false}}' > "$output"
  fi
  exit 0
fi

if [[ "$cmd" != "call" ]]; then
  echo "unexpected command: $cmd $sub" >&2
  exit 9
fi

prompt="$(jq -r '.messages[-1].content // empty' "$input")"
if [[ "$prompt" == *"Return only JSON"* || "$prompt" == *"previous extraction was invalid"* ]]; then
  if [[ "$prompt" == *"Drive the car"* ]]; then
    content='{"goal":{"object":"car","outcome":"wash","target_location":"car_wash"},"candidate_actions":[{"id":"drive-car-to-wash","moves":["person","car"],"recommendation":"drive","target_location":"car_wash"}],"objects_required":[{"current_location":"car_wash","object":"car","present_at_required_location":true,"required_location":"car_wash"}],"objects_moved":[{"action_id":"drive-car-to-wash","from":"home","object":"person","to":"car_wash"},{"action_id":"drive-car-to-wash","from":"home","object":"car","to":"car_wash"}],"resources":[{"id":"car","state":"at_car_wash","type":"vehicle"}],"constraints":[{"id":"car-must-be-at-wash","requirement":"car.location == car_wash before washing","type":"physical"}],"policy_context":{"distance_meters":50,"domain":"physical_planning"},"confidence":1}'
  else
    content='{"goal":{"object":"car","outcome":"wash","target_location":"car_wash"},"candidate_actions":[{"id":"walk-to-car-wash","moves":["person"],"recommendation":"walk","target_location":"car_wash"}],"objects_required":[{"current_location":"home","object":"car","present_at_required_location":false,"required_location":"car_wash"}],"objects_moved":[{"action_id":"walk-to-car-wash","from":"home","object":"person","to":"car_wash"}],"resources":[{"id":"car","state":"at_home","type":"vehicle"}],"constraints":[{"id":"car-must-be-at-wash","requirement":"car.location == car_wash before washing","type":"physical"}],"policy_context":{"distance_meters":50,"domain":"physical_planning"},"confidence":1}'
  fi
elif [[ "$prompt" == *"failed these feasibility checks"* ]]; then
  content="Drive the car to the car wash, or walk only if the car is already there."
else
  content="Walk to the car wash because it is nearby."
fi
jq -n --arg content "$content" '{result:{content:$content}}' > "$output"
EOF
chmod +x "$fake_cli"
live_solver="$(
  NXUSKIT_CLI="$fake_cli" \
  NXUSKIT_FAKE_SOLVER_LOG="$solver_log" \
  NXUSKIT_PROVIDER=ollama \
  NXUSKIT_MODEL=llama3:8b \
  bash "$BASH_MAIN" --scenario car-wash --mode live --guardrails solver --json
)"
solver_calls="$(cat "$solver_log")"
rm -rf "$tmp_cli_dir"
assert_eq "$(jq -r '.resolved_mode' <<<"$live_solver")" "live" "live solver mode"
assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$live_solver")" "solver" "live solver selection"
assert_eq "$(jq -r '.final_status' <<<"$live_solver")" "pass" "live solver final status"
assert_eq "$(jq -r '.stages[] | select(.id == "solver-proof") | .output.attempts[0].status' <<<"$live_solver")" "fail" "live solver first attempt"
assert_eq "$(jq -r '.stages[] | select(.id == "solver-proof") | .output.attempts[1].status' <<<"$live_solver")" "pass" "live solver repaired attempt"
assert_eq "$(jq -r '.stages[] | select(.id == "solver-proof") | .output.attempts[0].findings[0].evidence.runtime_executed' <<<"$live_solver")" "true" "live solver runtime label"
assert_eq "$(grep -c '^solver solve$' <<<"$solver_calls")" "2" "live solver CLI call count"

[[ -x "$SCRIPT_DIR/strict_live_smoke.sh" ]] || {
  echo "FAIL strict live smoke script must be executable" >&2
  exit 1
}
set +e
strict_gate_msg="$(RUN_LIVE_SMOKE=0 "$SCRIPT_DIR/strict_live_smoke.sh" 2>&1 >/dev/null)"
strict_gate_rc=$?
set -e
[[ "$strict_gate_rc" -eq 2 && "$strict_gate_msg" == *"RUN_LIVE_SMOKE=1"* ]] || {
  echo "FAIL strict live smoke should be gated behind RUN_LIVE_SMOKE=1" >&2
  echo "$strict_gate_msg" >&2
  exit 1
}

for required in problem.json expected-output.json rules.clp mock-baseline.json mock-facts.json mock-corrected-facts.json mock-repair.json mock-corrected.json; do
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
