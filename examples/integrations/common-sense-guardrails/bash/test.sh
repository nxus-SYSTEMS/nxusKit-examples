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
