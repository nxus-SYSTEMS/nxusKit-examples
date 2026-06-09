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
live_bn="$(
  NXUSKIT_CLI="$fake_cli" \
  NXUSKIT_FAKE_BN_LOG="$bn_log" \
  NXUSKIT_COMMON_SENSE_FIXTURE_LLM=1 \
  bash "$BASH_MAIN" --scenario coupon-stack --mode live --guardrails bn --json
)"
bn_calls="$(cat "$bn_log")"
rm -rf "$tmp_cli_dir"
assert_eq "$(jq -r '.resolved_mode' <<<"$live_bn")" "live" "fixture live BN mode"
assert_eq "$(jq -r '.guardrail_selection.selected | join(",")' <<<"$live_bn")" "bn" "fixture live BN selection"
assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .source' <<<"$live_bn")" "live" "fixture live BN source"
assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .output.attempts[0].status' <<<"$live_bn")" "fail" "fixture live BN first attempt"
assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .output.attempts[1].status' <<<"$live_bn")" "pass" "fixture live BN repaired attempt"
assert_eq "$(jq -r '.stages[] | select(.id == "bn-risk") | .output.attempts[0].findings[0].evidence.runtime_executed' <<<"$live_bn")" "true" "fixture live BN runtime label"
assert_eq "$(grep -c '^bn infer$' <<<"$bn_calls")" "2" "fixture live BN CLI call count"

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
