#!/usr/bin/env bash
# Vision / Multimodal — Bash CLI Example
#
# Demonstrates: provider capability discovery plus nxuskit-cli call with
# --image-url for multimodal requests.
#
# Usage:
#   bash main.sh                         # Claude metadata + live call if key is present
#   bash main.sh openai                  # Use OpenAI
#   VISION_RUN_LIVE=0 bash main.sh       # Probe and build request only
#   bash main.sh --verbose               # Show CLI commands + raw JSON

set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

provider="${VISION_PROVIDER:-${REMAINING_ARGS[0]:-claude}}"
image_url="${VISION_IMAGE_URL:-https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png}"
run_live="${VISION_RUN_LIVE:-auto}"

case "$provider" in
    claude)
        model="${VISION_MODEL:-claude-haiku-4-5-20251001}"
        key_var="ANTHROPIC_API_KEY"
        ;;
    openai)
        model="${VISION_MODEL:-gpt-4o-mini}"
        key_var="OPENAI_API_KEY"
        ;;
    ollama)
        model="${VISION_MODEL:-${OLLAMA_VISION_MODEL:-llava}}"
        key_var=""
        ;;
    *)
        model="${VISION_MODEL:-default}"
        key_var=""
        ;;
esac

echo "=== Vision / Multimodal CLI Demo ==="
echo "Provider: $provider"
echo "Model: $model"
echo "Image URL: $image_url"
echo

step_pause "Checking provider vision capability..." \
    "nxusKit CLI: provider info exposes stable capability metadata" \
    "The Bash flow checks vision support before attempting an image request"

info="$(tmpfile provider-info.json)"
if [[ $VERBOSE -eq 1 ]]; then
    echo "[CMD] $NXUSKIT_CLI provider info $provider --json"
fi
"$NXUSKIT_CLI" provider info "$provider" --json > "$info"

vision=$(jq -r '.result.capabilities.vision // false' "$info")
auth_status=$(jq -r '.result.auth_status // "unknown"' "$info")
echo "Vision capable: $vision"
echo "Auth status: $auth_status"

if [[ "$vision" != "true" ]]; then
    die "Provider '$provider' does not advertise vision support"
fi

req="$(tmpfile vision-request.json)"
jq --arg model "$model" '.model = $model' "$SCRIPT_DIR/requests/vision-request.json" > "$req"

echo
echo "Prepared multimodal request:"
jq '{model, max_tokens, messages}' "$req"
echo

if [[ "$run_live" == "0" || "$run_live" == "false" ]]; then
    echo "Live vision call skipped by VISION_RUN_LIVE=0."
    exit 0
fi

if [[ -n "$key_var" && -z "${!key_var:-}" ]]; then
    echo "Live vision call skipped because $key_var is not set."
    echo "Set $key_var in your environment, or run with VISION_RUN_LIVE=0 for metadata-only mode."
    if [[ "$run_live" == "1" || "$run_live" == "true" ]]; then
        exit 1
    fi
    exit 0
fi

step_pause "Sending image request..." \
    "nxusKit CLI: call accepts --image-url and provider/model overrides" \
    "The output envelope includes result content, usage, and trace metadata"

out="$(tmpfile vision-output.json)"
err="$(tmpfile vision-error.json)"
if [[ $VERBOSE -eq 1 ]]; then
    echo "[CMD] $NXUSKIT_CLI call --provider $provider --model $model --image-url $image_url --input $req --format json"
fi

if ! "$NXUSKIT_CLI" call --provider "$provider" --model "$model" --image-url "$image_url" --input "$req" --format json > "$out" 2>"$err"; then
    echo "Vision call failed."
    cat "$err" >&2
    exit 1
fi

echo "Response:"
jq -r '.result.content // .content // "No content returned"' "$out"
echo
echo "Trace: $(jq -r '.trace_id // "n/a"' "$out")"
echo "Done."
