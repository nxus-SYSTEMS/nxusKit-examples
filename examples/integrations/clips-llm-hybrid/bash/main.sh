#!/usr/bin/env bash
# CLIPS-LLM Hybrid — Bash CLI Example
#
# Demonstrates: 3-step hybrid pipeline: LLM classify → CLIPS route → LLM respond
# Uses nxuskit-cli call + clips eval for ticket routing.
#
# Usage:
#   bash main.sh                # Run with sample tickets
#   bash main.sh --verbose      # Show CLI commands + raw JSON
#   bash main.sh --step         # Step through with pauses

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"
parse_args "$@"
check_prereqs

echo "=== CLIPS-LLM Hybrid (Ticket Routing) Demo ==="
echo

# Sample support tickets
tickets=(
    "I was charged twice for my subscription last month and I want a refund immediately!"
    "My application keeps crashing with error code 500 when I try to upload files larger than 10MB."
    "Someone accessed my account from an unknown location. I need my password reset urgently!"
)

rules_file="$SCRIPT_DIR/../ticket-routing.clp"
if [[ ! -f "$rules_file" ]]; then
    die "CLIPS rules file not found: $rules_file"
fi

# Read CLIPS rules content
rules_content=$(cat "$rules_file")

for i in "${!tickets[@]}"; do
    ticket="${tickets[$i]}"
    idx=$((i + 1))

    echo "=== Ticket $idx ==="
    echo "Input: ${ticket:0:60}..."
    echo

    # --- Stage 1: LLM Classification ---
    step_pause "Stage 1: LLM classifying ticket..." \
        "nxusKit CLI: call to classify ticket (category, priority, sentiment)" \
        "Pattern 3: Dynamic request construction via jq"

    classify_req="$(tmpfile "classify-req-${idx}.json")"
    jq --arg ticket "$ticket" '.messages[1].content = $ticket' \
        "$SCRIPT_DIR/requests/classify-request.json" > "$classify_req"

    classify_out="$(tmpfile "classify-out-${idx}.json")"
    if ! run_cli call --provider ollama -i "$classify_req" -f json -o "$classify_out"; then
        echo "  Classification failed, skipping ticket."
        echo
        continue
    fi

    classification=$(jq -r '.result.content' "$classify_out")
    echo "Classification: $classification"
    echo

    # Parse classification fields (best effort)
    category=$(echo "$classification" | jq -r '.category // "general"' 2>/dev/null || echo "general")
    priority=$(echo "$classification" | jq -r '.priority // "medium"' 2>/dev/null || echo "medium")
    sentiment=$(echo "$classification" | jq -r '.sentiment // "neutral"' 2>/dev/null || echo "neutral")

    # --- Stage 2: CLIPS Routing ---
    step_pause "Stage 2: CLIPS routing based on classification..." \
        "nxusKit CLI: clips eval asserts classification facts and runs routing rules" \
        "Rules determine team, SLA hours, and escalation level"

    clips_input="$(tmpfile "clips-input-${idx}.json")"
    cat > "$clips_input" <<CLIPS_JSON
{
    "rules": $(jq -Rs '.' <<< "$rules_content"),
    "facts": [
        "(ticket-classification (category $category) (priority $priority) (sentiment $sentiment))"
    ],
    "queries": ["routing-decision"]
}
CLIPS_JSON

    clips_out="$(tmpfile "clips-out-${idx}.json")"
    if run_cli clips eval -i "$clips_input" -f json -o "$clips_out" 2>/dev/null; then
        echo "Routing Decision:"
        jq -r '.result.derived_facts // [] | .[] | "  Team: \(.slots.team // "unknown"), SLA: \(.slots["sla-hours"] // .slots.sla_hours // "?")h, Escalation: \(.slots["escalation-level"] // .slots.escalation_level // "?")"' "$clips_out" 2>/dev/null || echo "  (no routing decision derived)"

        team=$(jq -r '(.result.derived_facts // [])[0].slots.team // "support"' "$clips_out" 2>/dev/null || echo "support")
        sla=$(jq -r '(.result.derived_facts // [])[0].slots["sla-hours"] // "24"' "$clips_out" 2>/dev/null || echo "24")
    else
        echo "  CLIPS routing unavailable, using default routing."
        team="support"
        sla="24"
    fi
    echo

    # --- Stage 3: LLM Response Generation ---
    step_pause "Stage 3: LLM generating support response..." \
        "nxusKit CLI: call with routing context to generate empathetic response" \
        "Pattern 3: Dynamic request construction with routing info"

    response_context="Customer ticket: $ticket\n\nRouting: Team=$team, SLA=${sla}h, Category=$category, Priority=$priority, Sentiment=$sentiment"
    response_req="$(tmpfile "response-req-${idx}.json")"
    jq --arg ctx "$response_context" '.messages[1].content = $ctx' \
        "$SCRIPT_DIR/requests/response-request.json" > "$response_req"

    response_out="$(tmpfile "response-out-${idx}.json")"
    if run_cli call --provider ollama -i "$response_req" -f json -o "$response_out"; then
        echo "Suggested Response:"
        jq -r '.result.content' "$response_out" | head -5
    else
        echo "  Response generation failed."
    fi

    echo
    echo
done

echo "Done."
