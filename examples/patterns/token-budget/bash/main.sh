#!/usr/bin/env bash
# Token Budget — Bash CLI Example
#
# Demonstrates: nxuskit-cli call --stream --format jsonl with client-side
# budget accounting over streamed chunks.
#
# Usage:
#   bash main.sh                         # Loopback provider, no credentials
#   bash main.sh ollama                  # Use a local provider
#   TOKEN_BUDGET_MAX=40 bash main.sh     # Adjust the estimated token budget
#   bash main.sh --verbose               # Show CLI commands + JSONL stream

set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

provider="${TOKEN_BUDGET_PROVIDER:-${REMAINING_ARGS[0]:-loopback}}"
case "$provider" in
    loopback) default_model="echo" ;;
    ollama) default_model="${OLLAMA_MODEL:-llama3}" ;;
    claude) default_model="${ANTHROPIC_MODEL:-claude-haiku-4-5-20251001}" ;;
    openai) default_model="${OPENAI_MODEL:-gpt-4o-mini}" ;;
    *) default_model="${TOKEN_BUDGET_MODEL:-default}" ;;
esac
model="${TOKEN_BUDGET_MODEL:-$default_model}"
budget="${TOKEN_BUDGET_MAX:-12}"

if ! [[ "$budget" =~ ^[0-9]+$ ]] || [[ "$budget" -le 0 ]]; then
    die "TOKEN_BUDGET_MAX must be a positive integer"
fi

echo "=== Token Budget Streaming CLI Demo ==="
echo "Provider: $provider"
echo "Model: $model"
echo "Estimated token budget: $budget"
echo

step_pause "Preparing streaming request..." \
    "nxusKit CLI: call --stream --format jsonl returns machine-readable chunks" \
    "Bash tracks an estimated token budget while reading those chunks"

template="$SCRIPT_DIR/requests/story-request.json"
req_file="$(tmpfile request.json)"
jq --arg model "$model" '.model = $model' "$template" > "$req_file"

stream_fifo="$(tmpfile stream.fifo)"
stream_file="$(tmpfile stream.jsonl)"
err_file="$(tmpfile stream.err)"

if [[ $VERBOSE -eq 1 ]]; then
    echo "[CMD] $NXUSKIT_CLI call --provider $provider --stream --format jsonl --input $req_file"
fi

step_pause "Applying budget accounting..." \
    "Each content chunk increments a simple four-characters-per-token estimate" \
    "The Bash reader stops the CLI process when the budget is reached"

chars=0
chunks=0
budget_reached=0
content=""

mkfifo "$stream_fifo"
: > "$stream_file"
"$NXUSKIT_CLI" call --provider "$provider" --stream --format jsonl --input "$req_file" > "$stream_fifo" 2>"$err_file" &
cli_pid=$!

while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    printf '%s\n' "$line" >> "$stream_file"
    if [[ $VERBOSE -eq 1 ]]; then
        printf '[STREAM] %s\n' "$line"
    fi
    type=$(jq -r '.type // ""' <<<"$line")
    if [[ "$type" != "chunk" ]]; then
        continue
    fi
    delta=$(jq -r '.content // .delta // ""' <<<"$line")
    [[ -n "$delta" ]] || continue
    chunks=$((chunks + 1))
    chars=$((chars + ${#delta}))
    content+="$delta"
    estimated=$(((chars + 3) / 4))
    if [[ "$estimated" -ge "$budget" ]]; then
        budget_reached=1
        break
    fi
done < "$stream_fifo"

if [[ "$budget_reached" -eq 1 ]]; then
    kill "$cli_pid" 2>/dev/null || true
fi

if wait "$cli_pid"; then
    cli_status=0
else
    cli_status=$?
fi

if [[ "$cli_status" -ne 0 && "$budget_reached" -eq 0 ]]; then
    echo "Streaming call failed."
    cat "$err_file" >&2
    exit "$cli_status"
fi

if [[ "$chunks" -eq 0 ]]; then
    summary=$(jq -rs 'map(select(.type == "summary")) | .[0].content // ""' "$stream_file")
    if [[ -n "$summary" ]]; then
        chunks=1
        chars=${#summary}
        content="$summary"
    fi
fi

estimated=$(((chars + 3) / 4))

echo "=== Result ==="
echo "Chunks read: $chunks"
echo "Estimated tokens: $estimated / $budget"
echo "Budget reached: $([[ "$budget_reached" -eq 1 ]] && echo "Yes" || echo "No")"
echo "Content:"
echo "$content"
echo
echo "Done."
