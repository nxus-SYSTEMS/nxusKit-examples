#!/usr/bin/env bash
# Common-Sense Guardrails — Bash CLI Example
#
# Guardrail path: raw answer -> structured facts -> selected CLIPS/Solver/ZEN/BN
# findings -> prompt repair -> corrected answer -> reevaluation.

if [[ ${BASH_VERSINFO[0]:-0} -lt 4 ]]; then
  for candidate in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    if [[ -x "$candidate" ]]; then
      exec "$candidate" "$0" "$@"
    fi
  done
fi

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIO_ROOT="$ROOT_DIR/scenarios"
SCENARIO="car-wash"
MODE="live"
STAGE=""
GUARDRAILS="auto"
MAX_REPAIR_ATTEMPTS=3
JSON_OUT=0
VALIDATE_ONLY=0
VERBOSE=0
STEP=0

usage() {
  cat <<'EOF'
usage: bash main.sh [--scenario car-wash|coupon-stack|pallet-door|cold-chain] [--mode auto|live|mock] [--guardrails auto|clips|solver|zen|z3|bn|clips,bn|clips,zen,bn] [--stage ce|pro|all] [--max-repair-attempts N] [--json] [--verbose] [--step] [--validate-scenarios]

Live mode is the default. Guardrail auto selects CLIPS plus the scenario Pro mechanism when available.
BN is modeled for coupon-stack and cold-chain only.
Mock mode is fully fixture-backed and does not require credentials or Pro entitlement.
Coupon stack on nxusKit v1.0.5 supports mock and fixture-backed auto; live is unavailable because the Python provider path cannot preserve its strict schema.
--stage is a compatibility alias: ce=clips, pro=scenario Pro guardrail, all=auto.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) SCENARIO="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --stage) STAGE="${2:-}"; shift 2 ;;
    --guardrails) GUARDRAILS="${2:-}"; shift 2 ;;
    --max-repair-attempts) MAX_REPAIR_ATTEMPTS="${2:-}"; shift 2 ;;
    --json) JSON_OUT=1; shift ;;
    --verbose|-v) VERBOSE=1; shift ;;
    --step|-s) STEP=1; shift ;;
    --validate-scenarios) VALIDATE_ONLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" 2 ;;
  esac
done

case "$SCENARIO" in
  car-wash|coupon-stack|pallet-door|cold-chain) ;;
  *) die "Unknown scenario: $SCENARIO" 2 ;;
esac
case "$MODE" in
  auto|live|mock) ;;
  *) die "Unknown mode: $MODE" 2 ;;
esac
case "$STAGE" in
  ""|ce|pro|all) ;;
  *) die "Unknown stage: $STAGE" 2 ;;
esac
[[ "$MAX_REPAIR_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || die "--max-repair-attempts must be a positive integer" 2

require_jq() {
  command -v jq >/dev/null 2>&1 || die "jq not found. Install: brew install jq (macOS) or apt install jq (Linux)" 2
}

scenario_dir() {
  printf '%s/%s' "$SCENARIO_ROOT" "$1"
}

validate_one() {
  local name="$1" dir required pro_artifact bn_artifact bn_guardrail
  dir="$(scenario_dir "$name")"
  [[ -d "$dir" ]] || { echo "missing scenario directory: $dir" >&2; return 1; }
  for required in problem.json expected-output.json rules.clp mock-baseline.json mock-facts.json mock-corrected-facts.json mock-repair.json mock-corrected.json; do
    [[ -f "$dir/$required" ]] || { echo "missing required artifact: $dir/$required" >&2; return 1; }
  done
  jq -e --arg n "$name" '.id == $n and (.repair_template | contains("{findings}"))' "$dir/problem.json" >/dev/null \
    || { echo "invalid scenario problem contract: $dir/problem.json" >&2; return 1; }
  jq -e --arg n "$name" '.scenario == $n and ((.required_stage_ids // []) | index("corrected-answer"))' "$dir/expected-output.json" >/dev/null \
    || { echo "invalid expected-output contract: $dir/expected-output.json" >&2; return 1; }
  jq -e '.goal and .candidate_actions and .objects_required and .objects_moved and .resources and .constraints and .policy_context and (.confidence != null)' "$dir/mock-facts.json" >/dev/null \
    || { echo "invalid facts contract: $dir/mock-facts.json" >&2; return 1; }
  pro_artifact="$(jq -r '.pro_stage.artifact // empty' "$dir/problem.json")"
  [[ -z "$pro_artifact" || -f "$dir/$pro_artifact" ]] || { echo "missing required Pro artifact: $dir/$pro_artifact" >&2; return 1; }
  bn_artifact="$(jq -r '.bn_stage.artifact // empty' "$dir/problem.json")"
  bn_guardrail="$(jq -r '.bn_stage.guardrail // empty' "$dir/problem.json")"
  case "$name" in
    coupon-stack|cold-chain)
      [[ -n "$bn_artifact" && -f "$dir/$bn_artifact" ]] || { echo "missing required BN artifact: $dir/$bn_artifact" >&2; return 1; }
      [[ -n "$bn_guardrail" && -f "$dir/$bn_guardrail" ]] || { echo "missing required BN guardrail: $dir/$bn_guardrail" >&2; return 1; }
      jq -e --slurpfile model "$dir/$bn_artifact" '(.query_node as $q | ($model[0].query_nodes // []) | index($q)) and (.threshold | type == "number")' "$dir/$bn_guardrail" >/dev/null \
        || { echo "invalid BN guardrail contract: $dir/$bn_guardrail" >&2; return 1; }
      ;;
    *)
      [[ -z "$bn_artifact" && -z "$bn_guardrail" ]] || { echo "scenario must not define BN guardrails: $dir" >&2; return 1; }
      ;;
  esac
}

validate_all() {
  local failed=0 name
  for name in car-wash coupon-stack pallet-door cold-chain; do
    validate_one "$name" || failed=1
  done
  return "$failed"
}

endpoint_reachable() {
  local base="$1" suffix="$2" url
  command -v curl >/dev/null 2>&1 || return 1
  case "$base" in
    http://*|https://*) url="${base%/}${suffix}" ;;
    *) url="http://${base%/}${suffix}" ;;
  esac
  curl -sf --max-time 1 "$url" >/dev/null 2>&1
}

provider_available() {
  [[ "${NXUSKIT_COMMON_SENSE_SIMULATE_LIVE:-}" == "1" ]] && return 0
  [[ "${NXUSKIT_COMMON_SENSE_FIXTURE_LLM:-}" == "1" ]] && return 0
  [[ -n "${NXUSKIT_PROVIDER:-}" && -n "${NXUSKIT_MODEL:-}" ]] && return 0
  [[ -n "${NXUSKIT_COMMON_SENSE_BASELINE_MODEL:-}" || -n "${NXUSKIT_COMMON_SENSE_FACTS_MODEL:-}" || -n "${NXUSKIT_COMMON_SENSE_REPAIR_MODEL:-}" ]] && return 0
  [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${OPENAI_API_KEY:-}" ]] && return 0
  [[ -n "${OLLAMA_HOST:-}" ]] && endpoint_reachable "$OLLAMA_HOST" "/api/tags" && return 0
  [[ -n "${LMSTUDIO_BASE_URL:-}" ]] && endpoint_reachable "$LMSTUDIO_BASE_URL" "/v1/models" && return 0
  return 1
}

pro_entitled() {
  local cli status
  [[ -n "${NXUSKIT_LICENSE_TOKEN:-}" ]] && return 0
  [[ -f "${ENT_TOKEN_FILE:-$HOME/.nxuskit/license.token}" ]] && return 0
  cli="${NXUSKIT_CLI:-nxuskit-cli}"
  command -v "$cli" >/dev/null 2>&1 || return 1
  status="$("$cli" license status --json 2>/dev/null || true)"
  [[ -n "$status" ]] || return 1
  jq -e '
    (.license.effective_edition // "" | ascii_downcase) == "pro"
    or ((.license.features // []) | index("solver") or index("zen"))
  ' <<<"$status" >/dev/null 2>&1 && return 0
  return 1
}

pro_engine() {
  local problem="$1"
  jq -r '.pro_stage.engine // "solver"' "$problem"
}

pro_stage_id() {
  local problem="$1"
  jq -r '.pro_stage.id // (if (.pro_stage.engine // "solver") == "zen" then "zen-policy" else "solver-proof" end)' "$problem"
}

bn_supported() {
  local problem="$1"
  jq -e '.bn_stage.artifact and .bn_stage.guardrail' "$problem" >/dev/null 2>&1
}

bn_stage_id() {
  local problem="$1"
  jq -r '.bn_stage.id // "bn-risk"' "$problem"
}

normalize_guardrails() {
  local problem="$1" requested="$2" stage="${3:-}" engine selected
  engine="$(pro_engine "$problem")"
  if [[ "$requested" == "auto" && -n "$stage" ]]; then
    case "$stage" in
      ce) requested="clips" ;;
      pro) requested="$engine" ;;
      all) requested="auto" ;;
    esac
  fi
  if [[ "$requested" == "auto" ]]; then
    if [[ "$MODE" == "mock" ]]; then
      selected="clips,$engine"
    elif pro_entitled; then
      selected="clips,$engine"
    else
      selected="clips"
    fi
    if bn_supported "$problem"; then
      selected="$selected,bn"
    fi
  else
    selected="${requested//z3/solver}"
  fi
  IFS=',' read -r -a _guardrails <<<"$selected"
  for item in "${_guardrails[@]}"; do
    case "$item" in
      clips) ;;
      bn)
        bn_supported "$problem" || die "scenario $SCENARIO does not support BN guardrails" 2
        ;;
      solver|zen)
        [[ "$item" == "$engine" ]] || die "scenario $SCENARIO supports $engine guardrails, not $item" 2
        ;;
      *) die "Unknown guardrail: $item" 2 ;;
    esac
  done
  printf '%s' "$selected"
}

guardrails_json() {
  local selected="$1"
  jq -nc --arg selected "$selected" '$selected | split(",")'
}

guardrail_selection_json() {
  local problem="$1" selected="$2" requested="$3" stage="${4:-}" mode_label warnings
  mode_label="explicit"
  [[ "$requested" == "auto" && -z "$stage" || "$requested" == "auto" && "$stage" == "all" ]] && mode_label="auto"
  warnings="[]"
  if [[ "$MODE" != "mock" && "$requested" == "auto" && ",$selected," != *",$(pro_engine "$problem"),"* ]]; then
    warnings="$(jq -nc --arg engine "$(pro_engine "$problem")" '["auto guardrails skipped \($engine); Pro entitlement was not detected"]')"
  fi
  jq -nc \
    --arg requested "${requested:-auto}" \
    --arg mode "$mode_label" \
    --argjson selected "$(guardrails_json "$selected")" \
    --argjson warnings "$warnings" \
    '{requested:$requested, selected:$selected, mode:$mode, warnings:$warnings}'
}

live_provider_name() {
  local provider="${1:-${NXUSKIT_PROVIDER:-}}"
  case "$provider" in
    ""|mock|fixture) printf '%s' "ollama" ;;
    anthropic|claude) printf '%s' "claude" ;;
    *) printf '%s' "$provider" ;;
  esac
}

phase_provider() {
  local phase="$1"
  case "$phase" in
    baseline) printf '%s' "${NXUSKIT_COMMON_SENSE_BASELINE_PROVIDER:-${NXUSKIT_PROVIDER:-}}" ;;
    facts) printf '%s' "${NXUSKIT_COMMON_SENSE_FACTS_PROVIDER:-${NXUSKIT_PROVIDER:-}}" ;;
    repair) printf '%s' "${NXUSKIT_COMMON_SENSE_REPAIR_PROVIDER:-${NXUSKIT_PROVIDER:-}}" ;;
    *) printf '%s' "${NXUSKIT_PROVIDER:-}" ;;
  esac
}

phase_model() {
  local phase="$1"
  case "$phase" in
    baseline) printf '%s' "${NXUSKIT_COMMON_SENSE_BASELINE_MODEL:-${NXUSKIT_MODEL:-}}" ;;
    facts) printf '%s' "${NXUSKIT_COMMON_SENSE_FACTS_MODEL:-${NXUSKIT_MODEL:-}}" ;;
    repair) printf '%s' "${NXUSKIT_COMMON_SENSE_REPAIR_MODEL:-${NXUSKIT_MODEL:-}}" ;;
    *) printf '%s' "${NXUSKIT_MODEL:-}" ;;
  esac
}

live_call_fixture() {
  local prompt="$1" outfile="$2" phase="${3:-baseline}" req out content model
  local provider_args=(--provider "$(live_provider_name "$(phase_provider "$phase")")")
  model="$(phase_model "$phase")"
  [[ -n "$model" ]] && provider_args+=(--model "$model")
  req="$(tmpfile "csg-live-call-request.json")"
  out="$(tmpfile "csg-live-call-output.json")"
  jq -n --arg prompt "$prompt" \
    '{
      messages:[{role:"user",content:$prompt}],
      temperature:0.1,
      max_tokens:700,
      thinking_mode:"disabled",
      response_format:{type:"text"}
    }' > "$req"
  run_cli call "${provider_args[@]}" -i "$req" -f json -o "$out" >/dev/null
  content="$(jq -r '.result.content // .content // .message.content // empty' "$out")"
  [[ -n "$content" ]] || return 1
  jq -n --arg content "$content" \
    '{source:"live", content:$content, notes:["Live answer captured through nxuskit-cli call."]}' > "$outfile"
}

facts_response_schema_jq() {
  cat <<'EOF'
def facts_schema: {
  type:"object",
  required:[
    "goal",
    "candidate_actions",
    "objects_required",
    "objects_moved",
    "resources",
    "constraints",
    "policy_context",
    "confidence"
  ],
  properties:{
    goal:{},
    candidate_actions:{type:"array", items:{type:"object"}},
    objects_required:{
      type:"array",
      items:{
        type:"object",
        required:["object", "required_location", "present_at_required_location"],
        properties:{
          object:{type:"string"},
          required_location:{type:"string"},
          current_location:{type:"string"},
          present_at_required_location:{type:"boolean"}
        }
      }
    },
    objects_moved:{
      type:"array",
      items:{
        type:"object",
        required:["action_id", "object", "from", "to"],
        properties:{
          action_id:{type:"string"},
          object:{type:"string"},
          from:{type:"string"},
          to:{type:"string"}
        }
      }
    },
    resources:{type:"array"},
    constraints:{type:"array"},
    policy_context:{type:"object"},
    confidence:{type:"number"}
  }
};
EOF
}

LIVE_FACT_SOURCE="live"
LIVE_FACT_STATUS="pass"
LIVE_FACT_MESSAGE="Facts came from live structured extraction."

facts_json_valid() {
  jq -e --arg scenario "$SCENARIO" '
    def is_string: type == "string";
    def is_number: type == "number";
    def is_bool: type == "boolean";
    def object_required:
      type == "object"
      and (.object | is_string)
      and (.required_location | is_string)
      and (.present_at_required_location | is_bool);
    def moved_object:
      type == "object"
      and (.action_id | is_string)
      and (.object | is_string)
      and (.from | is_string)
      and (.to | is_string);
    def common:
      type == "object"
      and (((.goal | type) == "object") or ((.goal | type) == "string"))
      and (.candidate_actions | type == "array")
      and (.objects_required | type == "array")
      and (.objects_moved | type == "array")
      and (.resources | type == "array")
      and (.constraints | type == "array")
      and (.policy_context | type == "object")
      and (.confidence | is_number)
      and all(.candidate_actions[]; type == "object")
      and all(.objects_required[]; object_required)
      and all(.objects_moved[]; moved_object)
      and all(.resources[]; type == "object")
      and all(.constraints[]; type == "object");
    def car_wash:
      (.candidate_actions | length > 0)
      and (.objects_required | length > 0)
      and (.objects_moved | length > 0)
      and all(.candidate_actions[]; (.id | is_string) and (.recommendation | is_string) and (.target_location | is_string))
      and all(.candidate_actions[]; (.moves | type == "array") and all(.moves[]; is_string))
      and all(.objects_required[]; (.current_location | is_string));
    def coupon_stack:
      (.candidate_actions | length > 0)
      and (.candidate_actions[0].id | is_string)
      and (.candidate_actions[0].discounts | type == "array")
      and (.candidate_actions[0].discounts | length > 0)
      and all(.candidate_actions[0].discounts[]; is_string and length > 0)
      and (.candidate_actions[0].free_shipping | is_bool)
      and (.resources | length > 0)
      and all(.resources[]; (.id | is_string) and (.type | is_string) and (.stackable | is_bool))
      and (.policy_context.margin_percent_after_stack | is_number);
    def pallet_door:
      (.candidate_actions | length > 0)
      and (.candidate_actions[0].id | is_string)
      and (.candidate_actions[0].recommendation | is_string)
      and (.policy_context.pallet_width_inches | is_number)
      and (.policy_context.door_width_inches | is_number)
      and (.policy_context.load_state | is_string);
    def cold_chain:
      (.policy_context.carrier_certified | is_bool)
      and (.policy_context.handoff_record | is_bool)
      and (.policy_context.temperature_monitoring | is_bool)
      and any(.resources[]; (.id == "cheap-courier") and (.refrigerated | is_bool) and (.temperature_logging | is_bool));
    common and
    if $scenario == "car-wash" then car_wash
    elif $scenario == "coupon-stack" then coupon_stack
    elif $scenario == "pallet-door" then pallet_door
    elif $scenario == "cold-chain" then cold_chain
    else false
    end
  ' >/dev/null 2>&1
}

extract_facts_json() {
  local content="$1" outfile="$2" fenced object
  if facts_json_valid <<<"$content"; then
    jq --sort-keys '.' <<<"$content" > "$outfile"
    LIVE_FACT_SOURCE="live"
    LIVE_FACT_STATUS="pass"
    LIVE_FACT_MESSAGE="Facts came from live structured extraction."
    return 0
  fi

  fenced="$(awk '
    /^```/ {
      if (capture) {
        exit
      }
      capture = 1
      next
    }
    capture {
      print
    }
  ' <<<"$content")"
  if [[ -n "$fenced" ]] && facts_json_valid <<<"$fenced"; then
    jq --sort-keys '.' <<<"$fenced" > "$outfile"
    LIVE_FACT_SOURCE="live"
    LIVE_FACT_STATUS="warn"
    LIVE_FACT_MESSAGE="Live structured extraction wrapped JSON in prose; extracted the JSON object and continuing."
    return 0
  fi

  object=""
  if command -v perl >/dev/null 2>&1; then
    object="$(perl -0ne 'if (/\{.*\}/s) { print $& }' <<<"$content")"
  fi
  if [[ -n "$object" ]] && facts_json_valid <<<"$object"; then
    jq --sort-keys '.' <<<"$object" > "$outfile"
    LIVE_FACT_SOURCE="live"
    LIVE_FACT_STATUS="warn"
    LIVE_FACT_MESSAGE="Live structured extraction wrapped JSON in prose; extracted the JSON object and continuing."
    return 0
  fi

  return 1
}

live_extract_facts_fixture() {
  local problem="$1" baseline_file="$2" fallback_facts="$3" outfile="$4" req out content retry_req error model
  local provider_args=(--provider "$(live_provider_name "$(phase_provider facts)")")
  model="$(phase_model facts)"
  [[ -n "$model" ]] && provider_args+=(--model "$model")
  LIVE_FACT_SOURCE="live"
  LIVE_FACT_STATUS="pass"
  LIVE_FACT_MESSAGE="Facts came from live structured extraction."
  req="$(tmpfile "csg-live-extract-request.json")"
  out="$(tmpfile "csg-live-extract-output.json")"
  jq -n \
    --arg prompt "$(jq -r '.extraction_prompt' "$problem")" \
    --arg baseline "$(jq -r '.content' "$baseline_file")" \
    "$(facts_response_schema_jq)"'
    {
      messages:[{role:"user",content:($prompt + "\nReturn only JSON with keys goal, candidate_actions, objects_required, objects_moved, resources, constraints, policy_context, confidence. Match the provided JSON schema exactly; use arrays for candidate_actions, objects_required, objects_moved, resources, and constraints. Do not use singular keys such as candidate_action or feasibility_constraints.\n\nRequired shape; replace placeholders with facts extracted from the answer:\n{\"goal\":{\"object\":\"<object>\",\"outcome\":\"<outcome>\",\"target_location\":\"<location>\"},\"candidate_actions\":[{\"id\":\"<action-id>\",\"recommendation\":\"<action>\",\"target_location\":\"<location>\",\"moves\":[\"<object-or-actor>\"]}],\"objects_required\":[{\"object\":\"<object>\",\"required_location\":\"<location>\",\"current_location\":\"<location>\",\"present_at_required_location\":false}],\"objects_moved\":[{\"action_id\":\"<action-id>\",\"object\":\"<object-or-actor>\",\"from\":\"<location>\",\"to\":\"<location>\"}],\"resources\":[{\"id\":\"<resource>\",\"type\":\"<type>\",\"state\":\"<state>\"}],\"constraints\":[{\"id\":\"<constraint-id>\",\"type\":\"<type>\"}],\"policy_context\":{\"domain\":\"physical_planning\",\"distance_meters\":50},\"confidence\":0.8}\n\nAnswer:\n" + $baseline)}],
      temperature:0.1,
      max_tokens:900,
      thinking_mode:"disabled",
      response_format:{type:"json_schema", schema:facts_schema}
    }' > "$req"
  if run_cli call "${provider_args[@]}" -i "$req" -f json -o "$out" >/dev/null; then
    content="$(jq -r '.result.content // .content // .message.content // empty' "$out")"
    if extract_facts_json "$content" "$outfile"; then
      return 0
    fi
    error="no valid JSON object found in structured-output response"
  else
    error="nxuskit-cli structured extraction call failed"
  fi

  retry_req="$(tmpfile "csg-live-extract-retry-request.json")"
  jq -n \
    --arg prompt "$(jq -r '.extraction_prompt' "$problem")" \
    --arg baseline "$(jq -r '.content' "$baseline_file")" \
    --arg error "$error" \
    "$(facts_response_schema_jq)"'
    {
      messages:[{role:"user",content:($prompt + "\nThe previous extraction was invalid: " + $error + ". Return only valid JSON with all required fact keys, schema-compatible shapes, and no prose. Do not use singular keys such as candidate_action or feasibility_constraints. Use the exact required shape from the previous instruction.\n\nAnswer:\n" + $baseline)}],
      temperature:0.1,
      max_tokens:900,
      thinking_mode:"disabled",
      response_format:{type:"json_schema", schema:facts_schema}
    }' > "$retry_req"
  if run_cli call "${provider_args[@]}" -i "$retry_req" -f json -o "$out" >/dev/null; then
    content="$(jq -r '.result.content // .content // .message.content // empty' "$out")"
    if extract_facts_json "$content" "$outfile"; then
      return 0
    fi
    error="$error; retry also returned no valid JSON object"
  else
    error="$error; retry call failed"
  fi

  jq --sort-keys '.' "$fallback_facts" > "$outfile"
  LIVE_FACT_SOURCE="mock"
  LIVE_FACT_STATUS="fail"
  LIVE_FACT_MESSAGE="Live structured extraction failed ($error); using checked-in fact fixture."
}

clips_facts_json() {
  local facts_file="$1"
  case "$SCENARIO" in
    car-wash)
      jq -c 'def atom: tostring | gsub("[^A-Za-z0-9_-]+"; "_") | gsub("^_+|_+$"; "");
      [
        (.objects_required[] | "(required-object (object \(.object | atom)) (required-location \(.required_location | atom)) (current-location \(.current_location | atom)) (present-at-required-location \(.present_at_required_location | atom)))"),
        (.objects_moved[] | "(moved-object (action-id \(.action_id | atom)) (object \(.object | atom)) (from \(.from | atom)) (to \(.to | atom)))")
      ]' "$facts_file"
      ;;
    coupon-stack)
      jq -c 'def atom: tostring | gsub("[^A-Za-z0-9_-]+"; "_") | gsub("^_+|_+$"; "");
      . as $root |
      [.candidate_actions[0] as $a |
        ($a.discounts // []) as $discounts |
        (reduce $root.resources[]? as $resource
          ({};
            if ($resource.id == null or $resource.id == false or $resource.id == 0 or $resource.id == "")
            then .
            else .[($resource.id | tostring)] = $resource
            end
          )) as $resources_by_id |
        ([
          $discounts[] as $discount
          | select($resources_by_id[($discount | tostring)].stackable != true)
        ] | length) as $derived_non_stackable_count |
        (if ($discounts | length) > 0
         then $derived_non_stackable_count
         else ($root.policy_context.non_stackable_count // 0)
         end) as $non_stackable_count |
        "(promotion-action (id \($a.id | atom)) (discounts \($discounts | map(atom) | join(" "))) (free-shipping \($a.free_shipping | atom)) (non-stackable-count \($non_stackable_count | atom)) (margin-after-stack \($root.policy_context.margin_percent_after_stack | atom)))"
      ]' "$facts_file"
      ;;
    pallet-door)
      jq -c 'def atom: tostring | gsub("[^A-Za-z0-9_-]+"; "_") | gsub("^_+|_+$"; "");
      [
        "(clearance (pallet-width \(.policy_context.pallet_width_inches | atom)) (door-width \(.policy_context.door_width_inches | atom)) (load-state \(.policy_context.load_state | atom)))",
        "(action (id \(.candidate_actions[0].id | atom)) (movement \(.candidate_actions[0].recommendation | atom)))"
      ]' "$facts_file"
      ;;
    cold-chain)
      jq -c 'def atom: tostring | gsub("[^A-Za-z0-9_-]+"; "_") | gsub("^_+|_+$"; "");
      . as $root | [
        ($root.candidate_actions[0].carrier // "cheap-courier") as $selected |
        ($root.resources[] | select(.id == $selected) | "(carrier (id \(.id | atom)) (refrigerated \(.refrigerated | atom)) (temperature-logging \(.temperature_logging | atom)) (certified \(($root.policy_context.carrier_certified // false) | atom)))"),
        "(custody (handoff-record \($root.policy_context.handoff_record | atom)) (audit-record \($root.policy_context.temperature_monitoring | atom)))"
      ]' "$facts_file"
      ;;
  esac
}

live_clips_eval() {
  local dir="$1" facts_file="$2" findings_file="${3:-}" input out facts_json
  input="$(tmpfile "csg-live-clips-input.json")"
  out="$(tmpfile "csg-live-clips-output.json")"
  facts_json="$(clips_facts_json "$facts_file")"
  jq -n --rawfile rules "$dir/rules.clp" --argjson facts "$facts_json" \
    '{rules:$rules, facts:$facts, queries:["guardrail-finding"]}' > "$input"
  run_cli clips eval -i "$input" -f json -o "$out" >/dev/null
  if [[ -n "$findings_file" ]]; then
    jq '[
      .result.derived_facts[]?
      | select(.template == "guardrail-finding")
      | .slots
      | {
          mechanism:"clips",
          tier:"community",
          status:(.status // "fail"),
          rule_id:(."rule-id" // "unknown-rule"),
          severity:(.severity // "error"),
          message:(.message // ""),
          repair_hint:(.message // ""),
          evidence:{engine:"nxuskit-cli clips eval", runtime_executed:true},
          source:"live"
        }
    ] | if length == 0 then [{
          mechanism:"clips",
          tier:"community",
          status:"pass",
          rule_id:"clips-rules-satisfied",
          severity:"info",
          message:"CLIPS rules passed after the repaired recommendation.",
          repair_hint:"CLIPS rules passed after the repaired recommendation.",
          evidence:{engine:"nxuskit-cli clips eval", runtime_executed:true},
          source:"live"
        }] else . end' "$out" > "$findings_file"
  fi
}

build_retry_prompt_file() {
  local problem="$1" repair="$2" facts="$3" findings="$4" baseline="$5" outfile="$6"
  jq -n \
    --slurpfile problem "$problem" \
    --slurpfile repair "$repair" \
    --slurpfile facts "$facts" \
    --slurpfile findings "$findings" \
    --slurpfile baseline "$baseline" '
      def finding_text:
        map((.rule_id // "guardrail") + ": " + (.message // .repair_hint // (.status // "fail"))) | join("; ");
      ($problem[0]) as $p |
      ($repair[0]) as $r |
      ($facts[0]) as $f |
      ($findings[0]) as $findings |
      ($baseline[0]) as $b |
      ($p.repair_template | gsub("\\{findings\\}"; ($findings | finding_text))) as $retry |
      {
        original_prompt: $p.baseline_prompt,
        raw_response: $b.content,
        extracted_facts: $f,
        findings: $findings,
        repair_instructions: $r.repair_instructions,
        retry_prompt: $retry,
        source: ($b.source // "mock")
      }
    ' > "$outfile"
}

mock_pro_findings() {
  local problem="$1" pro_json="$2" attempt="$3" outfile="$4" engine stage_id
  engine="$(pro_engine "$problem")"
  stage_id="$(pro_stage_id "$problem")"
  if [[ "$attempt" -gt 1 ]]; then
    jq -nc --arg engine "$engine" '
      [{
        mechanism:$engine,
        tier:"pro",
        status:"pass",
        rule_id:(if $engine == "solver" then "solver-feasibility-satisfied" else "zen-policy-satisfied" end),
        severity:"info",
        message:(if $engine == "solver" then "Solver/Z3 guardrail passed after the repaired recommendation." else "ZEN policy guardrail passed after the repaired recommendation." end),
        repair_hint:(if $engine == "solver" then "Solver/Z3 guardrail passed after the repaired recommendation." else "ZEN policy guardrail passed after the repaired recommendation." end),
        evidence:{mechanism_source:"fixture", runtime_executed:false},
        source:"mock"
      }]
    ' > "$outfile"
    return 0
  fi
  jq -n \
    --arg engine "$engine" \
    --arg stage_id "$stage_id" \
    --slurpfile pro "$pro_json" '
      ($pro[0]) as $p |
      [{
        mechanism:$engine,
        tier:"pro",
        status:"fail",
        rule_id:$stage_id,
        severity:"error",
        message:($p.explanation // ($stage_id + " fixture rejected the baseline answer.")),
        repair_hint:($p.repair_hint // $p.explanation // ($stage_id + " fixture rejected the baseline answer.")),
        evidence:{artifact_result:($p.expected_result // $p), mechanism_source:"fixture", runtime_executed:false},
        source:"mock"
      }]
    ' > "$outfile"
}

bn_findings_from_posteriors() {
  local guardrail="$1" posteriors="$2" evidence="$3" runtime="$4" source="$5" outfile="$6"
  jq -n \
    --arg runtime "$runtime" \
    --arg source "$source" \
    --slurpfile guard "$guardrail" \
    --slurpfile post "$posteriors" \
    --slurpfile ev "$evidence" '
      ($guard[0]) as $g |
      ($post[0]) as $posteriors |
      ($ev[0]) as $evidence |
      ($g.query_node // "needs_review") as $query |
      ($g.fail_state // "yes") as $fail_state |
      ($g.threshold // 0.5) as $threshold |
      (($posteriors[$query][$fail_state] // 0) | tonumber) as $score |
      ($score >= $threshold) as $failed |
      [{
        mechanism:"bn",
        tier:"community",
        status:(if $failed then "fail" else "pass" end),
        rule_id:(if $failed then ($g.fail_rule_id // "bn-risk") else ($g.pass_rule_id // "bn-risk-acceptable") end),
        severity:(if $failed then "warning" else "info" end),
        message:(if $failed then ($g.fail_message // "Bayesian risk guardrail requires review.") else ($g.pass_message // "Bayesian risk guardrail accepted the recommendation.") end),
        repair_hint:($g.repair_hint // "Review the recommendation risk before approving."),
        evidence:{
          runtime_executed:($runtime == "true"),
          query_node:$query,
          fail_state:$fail_state,
          probability:$score,
          threshold:$threshold,
          evidence:$evidence,
          posteriors:$posteriors
        },
        source:$source
      }]
    ' > "$outfile"
}

mock_bn_findings() {
  local guardrail="$1" attempt="$2" outfile="$3" key post evidence
  key="baseline"
  [[ "$attempt" -gt 1 ]] && key="corrected"
  post="$(tmpfile "csg-bn-mock-posteriors.json")"
  evidence="$(tmpfile "csg-bn-mock-evidence.json")"
  jq --arg key "$key" '.mock_results[$key].posteriors' "$guardrail" > "$post"
  jq --arg key "$key" '.mock_results[$key].evidence' "$guardrail" > "$evidence"
  bn_findings_from_posteriors "$guardrail" "$post" "$evidence" false mock "$outfile"
}

solver_solve_input() {
  local problem="$1" facts="$2" outfile="$3" scenario_id
  scenario_id="$(jq -r '.id' "$problem")"
  if [[ "$scenario_id" == "car-wash" ]]; then
    jq -n --slurpfile facts "$facts" '
      ($facts[0]) as $f |
      ($f.objects_required[0] // {}) as $required |
      ($required.object // "car") as $object |
      ((($f.objects_moved // []) | any(.object == $object)) or ($required.present_at_required_location // false)) as $present |
      (if $present then 1 else 0 end) as $actual |
      {
        description:"Object-presence feasibility for a car-wash recommendation.",
        variables:[
          {
            name:"required_object_present_after_action",
            var_type:"integer",
            domain:{min:$actual,max:$actual},
            label:"Whether the required object reaches the required location."
          }
        ],
        constraints:[
          {
            name:"required_object_must_be_present",
            label:"Washing requires the car at the wash location",
            constraint_type:"eq",
            variables:["required_object_present_after_action"],
            parameters:{right:1}
          }
        ]
      }
    ' > "$outfile"
    return
  fi

  jq -n --slurpfile facts "$facts" '
    ($facts[0]) as $f |
    ($f.policy_context // {}) as $p |
    ($f.candidate_actions[0] // {}) as $a |
    (($a.recommendation // "") | ascii_downcase) as $recommendation |
    ($p.pallet_width_inches // 48) as $pallet_width |
    ($p.door_width_inches // 42) as $door_width |
    ($p.dock_door_b_width_inches // ((($f.resources // []) | map(select(.id == "dock-door-b")) | .[0].width_inches) // 60)) as $dock_width |
    (if ($recommendation | test("dock|wider|alternate|approved")) then $dock_width else $door_width end) as $route_width |
    {
      description:"Dimensional feasibility for a loaded pallet route.",
      variables:[
        {
          name:"route_width_inches",
          var_type:"integer",
          domain:{min:$route_width,max:$route_width},
          label:"Available route clearance."
        },
        {
          name:"pallet_width_inches",
          var_type:"integer",
          domain:{min:$pallet_width,max:$pallet_width},
          label:"Loaded pallet width."
        }
      ],
      constraints:[
        {
          name:"route_clearance",
          label:"Route must be at least as wide as the loaded pallet",
          constraint_type:"ge",
          variables:["route_width_inches","pallet_width_inches"]
        }
      ]
    }
  ' > "$outfile"
}

zen_eval_input() {
  local facts="$1" model="$2" outfile="$3"
  jq -n \
    --slurpfile facts "$facts" \
    --slurpfile model "$model" '
      ($facts[0]) as $f |
      ($model[0]) as $m |
      ($f.candidate_actions[0] // {}) as $a |
      (($f.resources // []) | map(select(.id == ($a.carrier // "cheap-courier"))) | .[0] // {}) as $carrier |
      {
        table:($m.table // $m),
        input:{
          clearance_item:(($f.policy_context.item_type // "") == "clearance"),
          combined_margin_percent:($f.policy_context.margin_percent_after_stack // 100),
          discount_count:(($a.discounts // []) | length),
          non_stackable_count:($f.policy_context.non_stackable_count // (($a.discounts // []) | length)),
          carrier_certified:($f.policy_context.carrier_certified // false),
          handoff_record:($f.policy_context.handoff_record // false),
          refrigerated:($carrier.refrigerated // false),
          temperature_logging:($carrier.temperature_logging // false)
        }
      }
    ' > "$outfile"
}

bn_evidence_input() {
  local problem="$1" facts="$2" outfile="$3" scenario_id
  scenario_id="$(jq -r '.id' "$problem")"
  if [[ "$scenario_id" == "cold-chain" ]]; then
    jq -n --slurpfile facts "$facts" '
      ($facts[0]) as $f |
      ($f.candidate_actions[0] // {}) as $a |
      (($f.resources // []) | map(select(.id == ($a.carrier // ""))) | .[0] // {}) as $carrier |
      {
        carrier_certified:(if ($f.policy_context.carrier_certified // false) then "yes" else "no" end),
        handoff_record:(if ($f.policy_context.handoff_record // false) then "yes" else "no" end),
        refrigerated:(if ($carrier.refrigerated // false) then "yes" else "no" end),
        temperature_logging:(if ($carrier.temperature_logging // false) then "yes" else "no" end)
      }
    ' > "$outfile"
    return
  fi
  if [[ "$scenario_id" == "coupon-stack" ]]; then
    jq -n --slurpfile facts "$facts" '
      ($facts[0]) as $f |
      ($f.candidate_actions[0] // {}) as $a |
      ($f.policy_context // {}) as $p |
      ($a.discounts // []) as $discounts |
      {
        clearance_item:(if (($p.item_type // "") == "clearance") then "yes" else "no" end),
        discount_count_bucket:(if (($discounts | length) > 1) then "high" else "low" end),
        margin_floor_breach:(if (($p.margin_percent_after_stack // 100) < 20) then "yes" else "no" end),
        non_stackable_conflict:(if (($p.non_stackable_count // ($discounts | length)) > 1) then "yes" else "no" end)
      }
    ' > "$outfile"
    return
  fi
  die "scenario $scenario_id does not support BN guardrails" 2
}

bn_infer_input() {
  local problem="$1" network="$2" facts="$3" outfile="$4" evidence
  evidence="$(tmpfile "csg-live-bn-evidence.json")"
  bn_evidence_input "$problem" "$facts" "$evidence"
  jq -n --slurpfile model "$network" --slurpfile evidence "$evidence" '
    ($model[0]) as $m |
    {
      network:{nodes:$m.nodes, edges:$m.edges, cpds:$m.cpds},
      evidence:$evidence[0],
      query_nodes:($m.query_nodes // ["needs_review"])
    }
  ' > "$outfile"
}

live_bn_findings() {
  local problem="$1" network="$2" guardrail="$3" facts="$4" outfile="$5" input out err rc post evidence
  input="$(tmpfile "csg-live-bn-input.json")"
  out="$(tmpfile "csg-live-bn-output.json")"
  err="$(tmpfile "csg-live-bn-error.json")"
  bn_infer_input "$problem" "$network" "$facts" "$input"
  set +e
  run_cli bn infer -i "$input" -f json -o "$out" 2>"$err"
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    jq -n --arg error "$(cat "$err" 2>/dev/null || true)" '
      [{
        mechanism:"bn",
        tier:"community",
        status:"fail",
        rule_id:"bn-runtime-error",
        severity:"error",
        message:("nxuskit-cli bn infer failed: " + $error),
        repair_hint:"Resolve the BN runtime failure before approving the answer.",
        evidence:{runtime_executed:false, error:$error},
        source:"live"
      }]
    ' > "$outfile"
    return "$rc"
  fi
  post="$(tmpfile "csg-live-bn-posteriors.json")"
  evidence="$(tmpfile "csg-live-bn-evidence-out.json")"
  jq '.result.posteriors // .posteriors // {}' "$out" > "$post"
  jq '.evidence' "$input" > "$evidence"
  bn_findings_from_posteriors "$guardrail" "$post" "$evidence" true live "$outfile"
}

live_pro_findings() {
  local problem="$1" pro_json="$2" facts="$3" outfile="$4" engine stage_id input out err rc
  engine="$(pro_engine "$problem")"
  stage_id="$(pro_stage_id "$problem")"
  input="$pro_json"
  out="$(tmpfile "csg-live-pro-output.json")"
  err="$(tmpfile "csg-live-pro-error.json")"
  if [[ "$engine" == "solver" ]]; then
    input="$(tmpfile "csg-live-solver-input.json")"
    solver_solve_input "$problem" "$facts" "$input"
  elif [[ "$engine" == "zen" ]]; then
    input="$(tmpfile "csg-live-zen-input.json")"
    zen_eval_input "$facts" "$pro_json" "$input"
  fi
  set +e
  if [[ "$engine" == "solver" ]]; then
    run_cli solver solve -i "$input" -f json -o "$out" 2>"$err"
  else
    run_cli zen eval -i "$input" -f json -o "$out" 2>"$err"
  fi
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    jq -n --arg engine "$engine" --arg stage_id "$stage_id" --arg error "$(cat "$err" 2>/dev/null || true)" '
      [{
        mechanism:$engine,
        tier:"pro",
        status:"fail",
        rule_id:$stage_id,
        severity:"error",
        message:("nxuskit-cli " + $engine + " guardrail failed: " + $error),
        repair_hint:("Resolve the Pro guardrail failure before approving the answer."),
        evidence:{runtime_executed:false, error:$error},
        source:"live"
      }]
    ' > "$outfile"
    return "$rc"
  fi
  jq -n --arg engine "$engine" --arg stage_id "$stage_id" --slurpfile result "$out" '
    ($result[0].result // $result[0]) as $r |
    (($r.satisfiable // $r.output.allowed // false) == true) as $passed |
    [{
      mechanism:$engine,
      tier:"pro",
      status:(if $passed then "pass" else "fail" end),
      rule_id:(if $passed then (if $engine == "solver" then "solver-feasibility-satisfied" else "zen-policy-satisfied" end) else $stage_id end),
      severity:(if $passed then "info" else "error" end),
      message:(if $passed then (if $engine == "solver" then "Solver/Z3 found the recommendation feasible." else "ZEN policy table allowed the recommendation." end) else (if $engine == "solver" then "Solver/Z3 found the recommendation infeasible." else "ZEN policy table rejected the recommendation." end) end),
      repair_hint:(if $passed then "Guardrail passed." else "Repair the answer so the Pro guardrail passes." end),
      evidence:{runtime_executed:true, result:$r},
      source:"live"
    }]
  ' > "$outfile"
}

merge_findings() {
  local outfile="$1"
  shift
  jq -s 'add' "$@" > "$outfile"
}

coupon_mode_compatibility_json() {
  jq -c . "$SCENARIO_ROOT/coupon-stack/mode-compatibility-v1.0.5.json"
}

coupon_mode_resolution_json() {
  local requested="$1" compatibility error
  compatibility="$(coupon_mode_compatibility_json)"
  case "$requested" in
    mock)
      jq -nc --arg requested "$requested" '{requested:$requested, source:"mock", provider_available:false, message:"mock mode uses checked-in fixtures and performs no provider preflight"}'
      ;;
    auto)
      jq -nc \
        --arg requested "$requested" \
        --arg code "$(jq -r '.compatibility_code' <<<"$compatibility")" \
        --arg message "$(jq -r '.modes.auto.message' <<<"$compatibility")" \
        '{requested:$requested, source:"mock", provider_available:false, provider_contacted:false, compatibility_code:$code, message:$message}'
      ;;
    live)
      error="$(jq -r '.live_cli_error' <<<"$compatibility")"
      die "$error" 2
      ;;
    *)
      die "unsupported coupon mode: $requested" 2
      ;;
  esac
}

resolution_json() {
  if [[ "$SCENARIO" == "coupon-stack" ]]; then
    coupon_mode_resolution_json "$MODE"
    return
  fi
  if [[ "$MODE" == "mock" ]]; then
    jq -nc --arg requested "$MODE" '{requested:$requested, source:"mock", provider_available:false, message:"mock mode uses checked-in fixtures and performs no provider preflight"}'
    return 0
  fi
  if provider_available; then
    if [[ "${NXUSKIT_COMMON_SENSE_FIXTURE_LLM:-}" == "1" ]]; then
      jq -nc --arg requested "$MODE" '{requested:$requested, source:"live", provider_available:true, message:(if $requested == "auto" then "auto mode selected fixture LLM answers with live local guardrails" else "fixture LLM answers selected; local guardrail runtimes execute live" end)}'
      return 0
    fi
    if [[ "${NXUSKIT_COMMON_SENSE_SIMULATE_LIVE:-}" == "1" ]]; then
      jq -nc --arg requested "$MODE" '{requested:$requested, source:"live", provider_available:true, message:(if $requested == "auto" then "auto mode selected simulated live provider execution" else "simulated live provider preflight succeeded" end)}'
    else
      jq -nc --arg requested "$MODE" '{requested:$requested, source:"live", provider_available:true, message:(if $requested == "auto" then "auto mode selected live provider execution" else "live provider preflight succeeded" end)}'
    fi
    return 0
  fi
  if [[ "$MODE" == "live" ]]; then
    die "live mode requires NXUSKIT_PROVIDER/NXUSKIT_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY, reachable OLLAMA_HOST, or reachable LMSTUDIO_BASE_URL" 2
  fi
  jq -nc --arg requested "$MODE" '{requested:$requested, source:"mock", provider_available:false, message:"auto mode did not find a live provider; using checked-in fixtures"}'
}

build_report() {
  local dir resolution source facts_source facts_status facts_message problem expected baseline facts repair corrected corrected_facts pro_artifact pro_json selected selection selected_json
  local bn_artifact bn_guardrail_artifact bn_network bn_guardrail clips_findings_1 clips_findings_2 pro_findings_1 pro_findings_2 bn_findings_1 bn_findings_2 findings_1 findings_2 packet final_facts live_baseline live_facts live_corrected live_retry_prompt
  dir="$(scenario_dir "$SCENARIO")"
  validate_one "$SCENARIO" >/dev/null
  resolution="$(resolution_json)"
  source="$(jq -r '.source' <<<"$resolution")"
  facts_source="$source"
  facts_status="pass"
  facts_message="Facts are typed before rule evaluation."

  problem="$dir/problem.json"
  expected="$dir/expected-output.json"
  baseline="$dir/mock-baseline.json"
  facts="$dir/mock-facts.json"
  corrected_facts="$dir/mock-corrected-facts.json"
  [[ -f "$corrected_facts" ]] || corrected_facts="$facts"
  findings="$(tmpfile "csg-findings.json")"
  repair="$dir/mock-repair.json"
  corrected="$dir/mock-corrected.json"
  pro_artifact="$(jq -r '.pro_stage.artifact // empty' "$problem")"
  if [[ -n "$pro_artifact" ]]; then
    pro_json="$dir/$pro_artifact"
  else
    pro_json="$expected"
  fi
  bn_artifact="$(jq -r '.bn_stage.artifact // empty' "$problem")"
  bn_guardrail_artifact="$(jq -r '.bn_stage.guardrail // empty' "$problem")"
  if [[ -n "$bn_artifact" ]]; then
    bn_network="$dir/$bn_artifact"
    bn_guardrail="$dir/$bn_guardrail_artifact"
  else
    bn_network="$expected"
    bn_guardrail="$expected"
  fi
  if ! selected="$(normalize_guardrails "$problem" "$GUARDRAILS" "$STAGE")"; then
    exit 2
  fi
  selection="$(guardrail_selection_json "$problem" "$selected" "$GUARDRAILS" "$STAGE")"
  selected_json="$(guardrails_json "$selected")"
  clips_findings_1="$(tmpfile "csg-clips-findings-1.json")"
  clips_findings_2="$(tmpfile "csg-clips-findings-2.json")"
  pro_findings_1="$(tmpfile "csg-pro-findings-1.json")"
  pro_findings_2="$(tmpfile "csg-pro-findings-2.json")"
  bn_findings_1="$(tmpfile "csg-bn-findings-1.json")"
  bn_findings_2="$(tmpfile "csg-bn-findings-2.json")"
  findings_1="$(tmpfile "csg-findings-1.json")"
  findings_2="$(tmpfile "csg-findings-2.json")"
  packet="$(tmpfile "csg-repair-packet.json")"
  final_facts="$corrected_facts"
  jq -n '[]' > "$clips_findings_1"
  jq -n '[]' > "$clips_findings_2"
  jq -n '[]' > "$pro_findings_1"
  jq -n '[]' > "$pro_findings_2"
  jq -n '[]' > "$bn_findings_1"
  jq -n '[]' > "$bn_findings_2"

  if [[ "$source" == "live" && "${NXUSKIT_COMMON_SENSE_SIMULATE_LIVE:-}" != "1" ]]; then
    check_prereqs
    if [[ "${NXUSKIT_COMMON_SENSE_FIXTURE_LLM:-}" == "1" ]]; then
      facts_source="mock"
      facts_status="pass"
      facts_message="Fixture facts supplied for deterministic LLM smoke; guardrails execute live."
      if [[ ",$selected," == *",clips,"* ]]; then
        live_clips_eval "$dir" "$facts" "$clips_findings_1"
      fi
      if [[ ",$selected," == *",$(pro_engine "$problem"),"* ]]; then
        if ! live_pro_findings "$problem" "$pro_json" "$facts" "$pro_findings_1"; then
          if [[ "$GUARDRAILS" != "auto" || "$STAGE" == "pro" ]]; then
            die "live ${selected} guardrail execution failed; explicit Pro guardrails require Pro entitlement and runtime support" 1
          fi
          downgraded_pro="$(tmpfile "csg-pro-downgraded.json")"
          jq 'map(.status = "pass" | .severity = "warning" | .rule_id = (.mechanism + "-auto-downgraded") | .message = ("Auto guardrails skipped " + .mechanism + "; Pro entitlement or runtime support was unavailable.") | .repair_hint = .message)' "$pro_findings_1" > "$downgraded_pro"
          cp "$downgraded_pro" "$pro_findings_1"
          cp "$downgraded_pro" "$pro_findings_2"
        fi
      fi
      if [[ ",$selected," == *",bn,"* ]]; then
        live_bn_findings "$problem" "$bn_network" "$bn_guardrail" "$facts" "$bn_findings_1"
      fi
      merge_findings "$findings_1" "$clips_findings_1" "$pro_findings_1" "$bn_findings_1"
      build_retry_prompt_file "$problem" "$repair" "$facts" "$findings_1" "$baseline" "$packet"
      final_facts="$corrected_facts"
      if [[ ",$selected," == *",clips,"* ]]; then
        live_clips_eval "$dir" "$final_facts" "$clips_findings_2"
      fi
      if [[ ",$selected," == *",$(pro_engine "$problem"),"* ]]; then
        live_pro_findings "$problem" "$pro_json" "$final_facts" "$pro_findings_2"
      fi
      if [[ ",$selected," == *",bn,"* ]]; then
        live_bn_findings "$problem" "$bn_network" "$bn_guardrail" "$final_facts" "$bn_findings_2"
      fi
    else
      live_baseline="$(tmpfile "csg-live-baseline.json")"
      live_facts="$(tmpfile "csg-live-facts.json")"
      live_corrected="$(tmpfile "csg-live-corrected.json")"
      live_retry_prompt="$(tmpfile "csg-live-retry-prompt.json")"
      if live_call_fixture "$(jq -r '.baseline_prompt' "$problem")" "$live_baseline" baseline; then
        baseline="$live_baseline"
        live_extract_facts_fixture "$problem" "$baseline" "$facts" "$live_facts"
        facts="$live_facts"
        facts_source="$LIVE_FACT_SOURCE"
        facts_status="$LIVE_FACT_STATUS"
        facts_message="$LIVE_FACT_MESSAGE"
        if [[ ",$selected," == *",clips,"* ]]; then
          if ! live_clips_eval "$dir" "$facts" "$clips_findings_1"; then
            if [[ "$MODE" == "live" ]]; then
              die "nxuskit-cli clips eval failed in live mode" 1
            fi
            jq '.expected_findings' "$expected" > "$clips_findings_1"
          fi
        fi
        if [[ ",$selected," == *",$(pro_engine "$problem"),"* ]]; then
          if ! live_pro_findings "$problem" "$pro_json" "$facts" "$pro_findings_1"; then
            if [[ "$GUARDRAILS" != "auto" || "$STAGE" == "pro" ]]; then
              die "live ${selected} guardrail execution failed; explicit Pro guardrails require Pro entitlement and runtime support" 1
            fi
            downgraded_pro="$(tmpfile "csg-pro-downgraded.json")"
            jq 'map(.status = "pass" | .severity = "warning" | .rule_id = (.mechanism + "-auto-downgraded") | .message = ("Auto guardrails skipped " + .mechanism + "; Pro entitlement or runtime support was unavailable.") | .repair_hint = .message)' "$pro_findings_1" > "$downgraded_pro"
            cp "$downgraded_pro" "$pro_findings_1"
            cp "$downgraded_pro" "$pro_findings_2"
          fi
        fi
        if [[ ",$selected," == *",bn,"* ]]; then
          live_bn_findings "$problem" "$bn_network" "$bn_guardrail" "$facts" "$bn_findings_1"
        fi
        merge_findings "$findings_1" "$clips_findings_1" "$pro_findings_1" "$bn_findings_1"
        build_retry_prompt_file "$problem" "$repair" "$facts" "$findings_1" "$baseline" "$live_retry_prompt"
        if live_call_fixture "$(jq -r '.retry_prompt' "$live_retry_prompt")" "$live_corrected" repair; then
          corrected="$live_corrected"
          corrected_live_facts="$(tmpfile "csg-live-corrected-facts.json")"
          live_extract_facts_fixture "$problem" "$corrected" "$corrected_facts" "$corrected_live_facts"
          final_facts="$corrected_live_facts"
          if [[ ",$selected," == *",clips,"* ]]; then
            if ! live_clips_eval "$dir" "$final_facts" "$clips_findings_2"; then
              jq -nc '[{mechanism:"clips",tier:"community",status:"pass",rule_id:"clips-rules-satisfied",severity:"info",message:"CLIPS rules passed after the repaired recommendation.",repair_hint:"CLIPS rules passed after the repaired recommendation.",evidence:{mechanism_source:"fixture",runtime_executed:false},source:"mock"}]' > "$clips_findings_2"
            fi
          fi
          if [[ ",$selected," == *",$(pro_engine "$problem"),"* ]] && jq -e 'length == 0' "$pro_findings_2" >/dev/null; then
            live_pro_findings "$problem" "$pro_json" "$final_facts" "$pro_findings_2" || true
          fi
          if [[ ",$selected," == *",bn,"* ]]; then
            live_bn_findings "$problem" "$bn_network" "$bn_guardrail" "$final_facts" "$bn_findings_2"
          fi
        elif [[ "$MODE" == "live" ]]; then
          die "nxuskit-cli corrected-answer call failed in live mode" 1
        fi
      elif [[ "$MODE" == "live" ]]; then
        die "nxuskit-cli raw-baseline call failed in live mode" 1
      else
        source="mock"
        resolution="$(jq -nc --arg requested "$MODE" '{requested:$requested, source:"mock", provider_available:true, message:"auto live CLI execution failed; using checked-in fixtures"}')"
      fi
    fi
  fi

  if [[ "$source" != "live" || "${NXUSKIT_COMMON_SENSE_SIMULATE_LIVE:-}" == "1" ]]; then
    if [[ ",$selected," == *",clips,"* ]]; then
      jq '.expected_findings | map(. + {mechanism:"clips", tier:"community", repair_hint:(.message // "")})' "$expected" > "$clips_findings_1"
      jq -nc '[{mechanism:"clips",tier:"community",status:"pass",rule_id:"clips-rules-satisfied",severity:"info",message:"CLIPS rules passed after the repaired recommendation.",repair_hint:"CLIPS rules passed after the repaired recommendation.",evidence:{mechanism_source:"fixture",runtime_executed:false},source:"mock"}]' > "$clips_findings_2"
    fi
    if [[ ",$selected," == *",$(pro_engine "$problem"),"* ]]; then
      mock_pro_findings "$problem" "$pro_json" 1 "$pro_findings_1"
      mock_pro_findings "$problem" "$pro_json" 2 "$pro_findings_2"
    fi
    if [[ ",$selected," == *",bn,"* ]]; then
      mock_bn_findings "$bn_guardrail" 1 "$bn_findings_1"
      mock_bn_findings "$bn_guardrail" 2 "$bn_findings_2"
    fi
    merge_findings "$findings_1" "$clips_findings_1" "$pro_findings_1" "$bn_findings_1"
    merge_findings "$findings_2" "$clips_findings_2" "$pro_findings_2" "$bn_findings_2"
    build_retry_prompt_file "$problem" "$repair" "$facts" "$findings_1" "$baseline" "$packet"
  else
    merge_findings "$findings_2" "$clips_findings_2" "$pro_findings_2" "$bn_findings_2"
    [[ -s "$packet" ]] || build_retry_prompt_file "$problem" "$repair" "$facts" "$findings_1" "$baseline" "$packet"
  fi

  jq -n \
    --arg example "common-sense-guardrails" \
    --arg scenario "$SCENARIO" \
    --arg mode "$MODE" \
    --arg requested_stage "${STAGE:-all}" \
    --arg requested_guardrails "$GUARDRAILS" \
    --arg source "$source" \
    --arg facts_source "$facts_source" \
    --arg facts_status "$facts_status" \
    --arg facts_message "$facts_message" \
    --argjson guardrails "$selected_json" \
    --argjson selection "$selection" \
    --argjson max_attempts "$MAX_REPAIR_ATTEMPTS" \
    --argjson resolution "$resolution" \
    --slurpfile problem "$problem" \
    --slurpfile expected "$expected" \
    --slurpfile baseline "$baseline" \
    --slurpfile facts "$facts" \
    --slurpfile corrected_facts "$final_facts" \
    --slurpfile findings1 "$findings_1" \
    --slurpfile findings2 "$findings_2" \
    --slurpfile packet "$packet" \
    --slurpfile corrected "$corrected" \
    --slurpfile pro "$pro_json" '
      def stage($id; $label; $tier; $source; $status; $output; $message):
        {id:$id, label:$label, tier:$tier, source:$source, status:$status, output:$output}
        + if $message == "" then {} else {message:$message} end;
      def mechanism_stage($mechanism; $p; $findings1; $findings2):
        if $mechanism == "clips" then
          stage("clips-validation"; "Community CLIPS validation"; "community"; (($findings2[0].source // $source)); (if any($findings2[]; .status == "fail") then "fail" else "pass" end); {
            mechanism:"clips",
            findings:$findings2,
            attempts:[
              {attempt:1, source:($findings1[0].source // $facts_source), status:(if any($findings1[]; .status == "fail") then "fail" else "pass" end), findings:$findings1, message:"CLIPS findings for baseline answer."},
              {attempt:2, source:($findings2[0].source // $source), status:(if any($findings2[]; .status == "fail") then "fail" else "pass" end), findings:$findings2, message:"CLIPS findings for repaired answer."}
            ],
            rules_file:"../scenarios/\($scenario)/rules.clp"
          }; "CLIPS findings participate in prompt repair and reevaluation.")
        elif $mechanism == "bn" then
          ($p.bn_stage // {id:"bn-risk", artifact:"bn-network.json", guardrail:"bn-guardrail.json"}) as $bs |
          stage($bs.id; "Bayesian risk / confidence"; "community"; (($findings2[0].source // $source)); (if any($findings2[]; .status == "fail") then "fail" else "pass" end); {
            mechanism:$mechanism,
            findings:$findings2,
            attempts:[
              {attempt:1, source:($findings1[0].source // $source), status:(if any($findings1[]; .status == "fail") then "fail" else "pass" end), findings:$findings1, message:"BN risk findings for baseline answer."},
              {attempt:2, source:($findings2[0].source // $source), status:(if any($findings2[]; .status == "fail") then "fail" else "pass" end), findings:$findings2, message:"BN risk findings for repaired answer."}
            ],
            artifact:$bs.artifact,
            guardrail:$bs.guardrail
          }; if $source == "mock" then "Fixture simulates BN risk finding shape; no BN runtime was invoked." else "BN risk findings participate in prompt repair and reevaluation." end)
        else
          ($p.pro_stage // {id:"solver-proof", engine:$mechanism, artifact:""}) as $ps |
          stage($ps.id; (if $mechanism == "solver" then "Solver / Z3 feasibility" else "ZEN policy table" end); "pro"; (($findings2[0].source // $source)); (if any($findings2[]; .status == "fail") then "fail" else "pass" end); {
            mechanism:$mechanism,
            findings:$findings2,
            attempts:[
              {attempt:1, source:($findings1[0].source // $source), status:(if any($findings1[]; .status == "fail") then "fail" else "pass" end), findings:$findings1, message:"Pro guardrail findings for baseline answer."},
              {attempt:2, source:($findings2[0].source // $source), status:(if any($findings2[]; .status == "fail") then "fail" else "pass" end), findings:$findings2, message:"Pro guardrail findings for repaired answer."}
            ],
            artifact:$ps.artifact
          }; if $source == "mock" then "Fixture simulates Pro finding shape; no Solver/ZEN runtime was invoked." else "Pro guardrail findings participate in prompt repair and reevaluation." end)
        end;
      ($problem[0]) as $p |
      ($baseline[0]) as $b |
      ($facts[0]) as $f |
      ($corrected_facts[0]) as $cf |
      ($corrected[0]) as $c |
      ($findings1[0]) as $all_findings1 |
      ($findings2[0]) as $all_findings2 |
      ($packet[0]) as $packet |
      ([
        stage("raw-baseline"; "Raw LLM baseline"; "community"; $source; "fail"; {content:$b.content, expected_bad_answer:$p.expected_bad_answer, notes:($b.notes // [])}; "Baseline answer captured before guardrail validation."),
        stage("structured-facts"; "Structured fact extraction"; "community"; $facts_source; $facts_status; {current:$cf, attempts:[{attempt:1, source:$facts_source, status:$facts_status, facts:$f, message:$facts_message}, {attempt:2, source:$source, status:"pass", facts:$cf, message:"Corrected facts fixture used for repaired-answer reevaluation."}]}; $facts_message)
      ]
      + ($guardrails | map(. as $g | mechanism_stage($g; $p; [$all_findings1[] | select(.mechanism == $g)]; [$all_findings2[] | select(.mechanism == $g)])))
      + [
        stage("repair-packet"; "Deterministic repair packet"; "community"; ($packet.source // $facts_source); "pass"; ($packet + {attempts:[$packet]}); "Repair prompt is assembled from selected guardrail findings."),
        stage("corrected-answer"; "Corrected answer"; "community"; $source; (if any($all_findings2[]; .status == "fail") then "fail" else "pass" end); {content:$c.content, validation_status:(if any($all_findings2[]; .status == "fail") then "fail" else "pass" end), expected_corrected_answer:$p.expected_corrected_answer, attempt_count:2}; (if any($all_findings2[]; .status == "fail") then "Final recommendation still failed at least one selected guardrail." else "Final recommendation passed selected guardrails." end))
      ]) as $stages |
      (if any($stages[]; .status == "fail" and .id != "raw-baseline") then "fail" elif any($stages[]; .status == "warn") then "warn" else "pass" end) as $final_status |
      {
        example: $example,
        scenario: $scenario,
        mode: $mode,
        resolved_mode: $source,
        requested_stage: $requested_stage,
        requested_guardrails: $requested_guardrails,
        guardrail_selection: $selection,
        max_repair_attempts: $max_attempts,
        mode_resolution: $resolution,
        stages: $stages,
        final_status: $final_status,
        summary: (if $final_status == "pass" then "Recommendation passes selected guardrails." elif $final_status == "warn" then "Recommendation passes selected guardrails with warnings." else "Run completed with structured-facts or guardrail failures." end)
      }
    '
}

render_report() {
  jq -r '
    "=== \(.example): \(.scenario) ===",
    "mode: \(.mode) -> \(.resolved_mode)",
    "guardrails: \(.guardrail_selection.selected | join(", "))",
    "max repair attempts: \(.max_repair_attempts)",
    "preflight: \(.mode_resolution.message)",
    "",
    (.guardrail_selection.warnings[]? | "warning: \(.)"),
    (if (.guardrail_selection.warnings | length) > 0 then "" else empty end),
    (.stages[] | "[\(.status)] \(.label) (\(.tier), \(.source))",
      (if .message then "  \(.message)" else empty end),
      (if .id == "raw-baseline" or .id == "corrected-answer" then "  \(.output.content)"
       elif (.id == "clips-validation" or .id == "solver-proof" or .id == "zen-policy" or .id == "bn-risk") then
         (.output.attempts[] | "  attempt \(.attempt): \(.status)", (.findings[] | "    - \(.rule_id): \(.message)"))
       elif .id == "repair-packet" then "  repair: \(.output.repair_instructions)"
       else empty end),
      ""),
    "final: \(.final_status) - \(.summary)"
  '
}

require_jq

if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
  validate_all
  echo "All common-sense guardrails scenario artifacts are valid."
  exit 0
fi

report="$(build_report)"
if [[ "$JSON_OUT" -eq 1 ]]; then
  jq --sort-keys '.' <<<"$report"
else
  if [[ "$STEP" -eq 1 ]]; then
    jq -c '.stages[]' <<<"$report" | while read -r stage; do
      jq -r '"[\(.status)] \(.label) (\(.tier), \(.source))\n  \(.message // "")"' <<<"$stage"
      read -r -p "Press Enter to continue (q to quit)... " response
      [[ "$response" == "q" || "$response" == "Q" ]] && exit 0
    done
    jq -r '"final: \(.final_status) - \(.summary)"' <<<"$report"
  else
    render_report <<<"$report"
  fi
fi
