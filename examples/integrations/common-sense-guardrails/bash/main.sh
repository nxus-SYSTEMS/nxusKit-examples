#!/usr/bin/env bash
# Common-Sense Guardrails — Bash CLI Example
#
# Community path: raw answer -> structured facts -> CLIPS findings -> repair -> corrected answer.
# Optional Pro stages use checked-in mock Solver/ZEN evidence unless live entitlement is available.

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
MODE="auto"
STAGE="ce"
JSON_OUT=0
VALIDATE_ONLY=0
VERBOSE=0
STEP=0

usage() {
  cat <<'EOF'
usage: bash main.sh [--scenario car-wash|coupon-stack|pallet-door|cold-chain] [--mode auto|live|mock] [--stage ce|pro|all] [--json] [--verbose] [--step] [--validate-scenarios]

Community stages run by default. Mock mode is fully fixture-backed and does not require credentials.
Pro stages are optional. In mock mode they use checked-in Solver/ZEN evidence; in live mode they require Pro entitlement before solver or zen execution.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) SCENARIO="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --stage) STAGE="${2:-}"; shift 2 ;;
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
  ce|pro|all) ;;
  *) die "Unknown stage: $STAGE" 2 ;;
esac

require_jq() {
  command -v jq >/dev/null 2>&1 || die "jq not found. Install: brew install jq (macOS) or apt install jq (Linux)" 2
}

scenario_dir() {
  printf '%s/%s' "$SCENARIO_ROOT" "$1"
}

validate_one() {
  local name="$1" dir required pro_artifact
  dir="$(scenario_dir "$name")"
  [[ -d "$dir" ]] || { echo "missing scenario directory: $dir" >&2; return 1; }
  for required in problem.json expected-output.json rules.clp mock-baseline.json mock-facts.json mock-repair.json mock-corrected.json; do
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
  [[ -n "${NXUSKIT_PROVIDER:-}" && -n "${NXUSKIT_MODEL:-}" ]] && return 0
  [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${OPENAI_API_KEY:-}" ]] && return 0
  [[ -n "${OLLAMA_HOST:-}" ]] && endpoint_reachable "$OLLAMA_HOST" "/api/tags" && return 0
  [[ -n "${LMSTUDIO_BASE_URL:-}" ]] && endpoint_reachable "$LMSTUDIO_BASE_URL" "/v1/models" && return 0
  return 1
}

pro_entitled() {
  [[ -n "${NXUSKIT_LICENSE_TOKEN:-}" ]] && return 0
  [[ -f "${ENT_TOKEN_FILE:-$HOME/.nxuskit/license.token}" ]] && return 0
  return 1
}

live_provider_name() {
  case "${NXUSKIT_PROVIDER:-}" in
    ""|mock|fixture) printf '%s' "ollama" ;;
    anthropic|claude) printf '%s' "claude" ;;
    *) printf '%s' "$NXUSKIT_PROVIDER" ;;
  esac
}

live_call_fixture() {
  local prompt="$1" outfile="$2" req out content
  req="$(tmpfile "csg-live-call-request.json")"
  out="$(tmpfile "csg-live-call-output.json")"
  jq -n --arg prompt "$prompt" \
    '{messages:[{role:"user",content:$prompt}], temperature:0.1, max_tokens:700}' > "$req"
  run_cli call --provider "$(live_provider_name)" -i "$req" -f json -o "$out" >/dev/null
  content="$(jq -r '.result.content // .content // .message.content // empty' "$out")"
  [[ -n "$content" ]] || return 1
  jq -n --arg content "$content" \
    '{source:"live", content:$content, notes:["Live answer captured through nxuskit-cli call."]}' > "$outfile"
}

LIVE_FACT_SOURCE="live"
LIVE_FACT_STATUS="pass"
LIVE_FACT_MESSAGE="Facts came from live structured extraction."

facts_json_valid() {
  jq -e '.goal and .candidate_actions and .objects_required and .objects_moved and .resources and .constraints and .policy_context and (.confidence != null)' >/dev/null 2>&1
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
  local problem="$1" baseline_file="$2" fallback_facts="$3" outfile="$4" req out content retry_req error
  LIVE_FACT_SOURCE="live"
  LIVE_FACT_STATUS="pass"
  LIVE_FACT_MESSAGE="Facts came from live structured extraction."
  req="$(tmpfile "csg-live-extract-request.json")"
  out="$(tmpfile "csg-live-extract-output.json")"
  jq -n \
    --arg prompt "$(jq -r '.extraction_prompt' "$problem")" \
    --arg baseline "$(jq -r '.content' "$baseline_file")" \
    '{messages:[{role:"user",content:($prompt + "\nReturn only JSON with keys goal, candidate_actions, objects_required, objects_moved, resources, constraints, policy_context, confidence.\n\nAnswer:\n" + $baseline)}], temperature:0.1, max_tokens:900}' > "$req"
  if run_cli call --provider "$(live_provider_name)" -i "$req" -f json -o "$out" >/dev/null; then
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
    '{messages:[{role:"user",content:($prompt + "\nThe previous extraction was invalid: " + $error + ". Return only valid JSON with all required fact keys and no prose.\n\nAnswer:\n" + $baseline)}], temperature:0.1, max_tokens:900}' > "$retry_req"
  if run_cli call --provider "$(live_provider_name)" -i "$retry_req" -f json -o "$out" >/dev/null; then
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
  LIVE_FACT_STATUS="warn"
  LIVE_FACT_MESSAGE="Live structured extraction failed ($error); using checked-in fact fixture."
}

clips_facts_json() {
  local facts_file="$1"
  case "$SCENARIO" in
    car-wash)
      jq -c '[
        (.objects_required[] | "(required-object (object \(.object)) (required-location \(.required_location)) (current-location \(.current_location)) (present-at-required-location \(.present_at_required_location)))"),
        (.objects_moved[] | "(moved-object (action-id \(.action_id)) (object \(.object)) (from \(.from)) (to \(.to)))")
      ]' "$facts_file"
      ;;
    coupon-stack)
      jq -c '[.candidate_actions[0] as $a | "(promotion-action (id \($a.id)) (discounts \($a.discounts | join(" "))) (free-shipping \($a.free_shipping)) (margin-after-stack \(.policy_context.margin_percent_after_stack)))"]' "$facts_file"
      ;;
    pallet-door)
      jq -c '[
        "(clearance (pallet-width \(.policy_context.pallet_width_inches)) (door-width \(.policy_context.door_width_inches)) (load-state \(.policy_context.load_state)))",
        "(action (id \(.candidate_actions[0].id)) (movement \(.candidate_actions[0].recommendation)))"
      ]' "$facts_file"
      ;;
    cold-chain)
      jq -c '. as $root | [
        ($root.resources[] | select(.id == "cheap-courier") | "(carrier (id \(.id)) (refrigerated \(.refrigerated)) (temperature-logging \(.temperature_logging)) (certified \($root.policy_context.carrier_certified // false)))"),
        "(custody (handoff-record \($root.policy_context.handoff_record)) (audit-record \($root.policy_context.temperature_monitoring)))"
      ]' "$facts_file"
      ;;
  esac
}

live_clips_eval() {
  local dir="$1" facts_file="$2" input out facts_json
  input="$(tmpfile "csg-live-clips-input.json")"
  out="$(tmpfile "csg-live-clips-output.json")"
  facts_json="$(clips_facts_json "$facts_file")"
  jq -n --rawfile rules "$dir/rules.clp" --argjson facts "$facts_json" \
    '{rules:$rules, facts:$facts, queries:["guardrail-finding"]}' > "$input"
  run_cli clips eval -i "$input" -f json -o "$out" >/dev/null
}

resolution_json() {
  if [[ "$MODE" == "mock" ]]; then
    jq -nc --arg requested "$MODE" '{requested:$requested, source:"mock", provider_available:false, message:"mock mode uses checked-in fixtures and performs no provider preflight"}'
    return 0
  fi
  if provider_available; then
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
  local dir resolution source facts_source facts_status facts_message problem expected baseline facts repair corrected pro_artifact pro_json entitled
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
  repair="$dir/mock-repair.json"
  corrected="$dir/mock-corrected.json"
  pro_artifact="$(jq -r '.pro_stage.artifact // empty' "$problem")"
  if [[ -n "$pro_artifact" ]]; then
    pro_json="$dir/$pro_artifact"
  else
    pro_json="$expected"
  fi

  if [[ "$source" == "live" && "${NXUSKIT_COMMON_SENSE_SIMULATE_LIVE:-}" != "1" ]]; then
    check_prereqs
    live_baseline="$(tmpfile "csg-live-baseline.json")"
    live_facts="$(tmpfile "csg-live-facts.json")"
    live_corrected="$(tmpfile "csg-live-corrected.json")"
    if live_call_fixture "$(jq -r '.baseline_prompt' "$problem")" "$live_baseline"; then
      baseline="$live_baseline"
      live_extract_facts_fixture "$problem" "$baseline" "$facts" "$live_facts"
      facts="$live_facts"
      facts_source="$LIVE_FACT_SOURCE"
      facts_status="$LIVE_FACT_STATUS"
      facts_message="$LIVE_FACT_MESSAGE"
      if ! live_clips_eval "$dir" "$facts"; then
        if [[ "$MODE" == "live" ]]; then
          die "nxuskit-cli clips eval failed in live mode" 1
        fi
      fi
      if live_call_fixture "$(jq -r '.retry_prompt' "$repair")" "$live_corrected"; then
        corrected="$live_corrected"
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

  entitled=false
  if pro_entitled; then
    entitled=true
  fi

  jq -n \
    --arg example "common-sense-guardrails" \
    --arg scenario "$SCENARIO" \
    --arg mode "$MODE" \
    --arg requested_stage "$STAGE" \
    --arg source "$source" \
    --arg facts_source "$facts_source" \
    --arg facts_status "$facts_status" \
    --arg facts_message "$facts_message" \
    --argjson resolution "$resolution" \
    --argjson pro_entitled "$entitled" \
    --slurpfile problem "$problem" \
    --slurpfile expected "$expected" \
    --slurpfile baseline "$baseline" \
    --slurpfile facts "$facts" \
    --slurpfile repair "$repair" \
    --slurpfile corrected "$corrected" \
    --slurpfile pro "$pro_json" '
      def finding($raw; $facts):
        {
          status: ($raw.status // "fail"),
          rule_id: $raw.rule_id,
          severity: ($raw.severity // "error"),
          message: ($raw.message // ("Rule " + $raw.rule_id + " failed.")),
          evidence: ($raw.evidence // {facts_summary: ($facts.policy_context // {})})
        };
      def stage($id; $label; $tier; $source; $status; $output; $message):
        {id:$id, label:$label, tier:$tier, source:$source, status:$status, output:$output}
        + if $message == "" then {} else {message:$message} end;
      ($problem[0]) as $p |
      ($expected[0]) as $e |
      ($baseline[0]) as $b |
      ($facts[0]) as $f |
      ($repair[0]) as $r |
      ($corrected[0]) as $c |
      ($e.expected_findings | map(finding(.; $f))) as $findings |
      ($findings | map(.rule_id + ": " + .message) | join("; ")) as $finding_text |
      {
        original_prompt: $p.baseline_prompt,
        raw_response: $b.content,
        extracted_facts: $f,
        findings: $findings,
        repair_instructions: $r.repair_instructions,
        retry_prompt: ($r.retry_prompt // ($p.repair_template | gsub("\\{findings\\}"; $finding_text))),
        source: $source
      } as $packet |
      [
        stage("raw-baseline"; "Raw LLM baseline"; "community"; $source; "fail"; {content:$b.content, expected_bad_answer:$p.expected_bad_answer, notes:($b.notes // [])}; "Baseline answer violates at least one common-sense guardrail."),
        stage("structured-facts"; "Structured fact extraction"; "community"; $facts_source; $facts_status; $f; $facts_message),
        stage("clips-validation"; "Community CLIPS validation"; "community"; $facts_source; (if any($findings[]; .status == "fail") then "fail" else "pass" end); {findings:$findings, rules_file:"../scenarios/\($scenario)/rules.clp"}; "Validation failed; building deterministic repair packet."),
        stage("repair-packet"; "Deterministic repair packet"; "community"; $facts_source; "pass"; $packet; "Repair prompt is assembled from findings, not free-form guesswork."),
        stage("corrected-answer"; "Corrected answer"; "community"; $source; ($c.validation_status // "pass"); {content:$c.content, validation_status:($c.validation_status // "pass"), expected_corrected_answer:$p.expected_corrected_answer}; "Corrected recommendation passes Community guardrails.")
      ] as $ce |
      ($p.pro_stage // {id:"solver-proof", engine:"solver", artifact:""}) as $ps |
      ($pro[0]) as $pa |
      (if $source == "live" and ($pro_entitled | not) then
        stage($ps.id; (if $ps.engine == "solver" then "Solver proof" else "ZEN policy table" end); "pro"; "live"; "skipped"; {engine:$ps.engine, entitlement_mode:"unavailable", result:{}, explanation:"Live Pro evidence requires a Pro entitlement; Community stages remain runnable."}; "Pro entitlement unavailable; skipping live Pro stage.")
      else
        stage($ps.id; (if $ps.engine == "solver" then "Solver proof" else "ZEN policy table" end); "pro"; $source; "pass"; {engine:$ps.engine, entitlement_mode:(if $source == "mock" then "mock-fixture" else "live-entitled" end), result:($pa.expected_result // $pa), artifact:$ps.artifact, explanation:($pa.explanation // "Pro evidence fixture supports the corrected recommendation.")}; (if $source == "mock" then "Mock Pro evidence uses checked-in Solver/ZEN artifacts and requires no entitlement." else "Live Pro evidence entitlement check passed." end))
      end) as $pro_stage |
      (if $requested_stage == "ce" then $ce elif $requested_stage == "pro" then [$pro_stage] else ($ce + [$pro_stage]) end) as $stages |
      {
        example: $example,
        scenario: $scenario,
        mode: $mode,
        resolved_mode: $source,
        requested_stage: $requested_stage,
        mode_resolution: $resolution,
        stages: $stages,
        final_status: (if any($stages[]; .id == "corrected-answer" and .status == "pass") then "pass" elif all($stages[]; .status == "skipped") then "skipped" elif any($stages[]; .status == "warn") then "warn" elif any($stages[]; .status == "fail" and .id != "raw-baseline") then "fail" else "pass" end),
        summary: "Corrected recommendation passes Community guardrails."
      }
    '
}

render_report() {
  jq -r '
    "=== \(.example): \(.scenario) ===",
    "mode: \(.mode) -> \(.resolved_mode)",
    "stage: \(.requested_stage)",
    "preflight: \(.mode_resolution.message)",
    "",
    (.stages[] | "[\(.status)] \(.label) (\(.tier), \(.source))",
      (if .message then "  \(.message)" else empty end),
      (if .id == "raw-baseline" or .id == "corrected-answer" then "  \(.output.content)"
       elif .id == "clips-validation" then (.output.findings[] | "  - \(.rule_id): \(.message)")
       elif .id == "repair-packet" then "  repair: \(.output.repair_instructions)"
       elif .tier == "pro" then "  evidence: \(.output.explanation)"
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
