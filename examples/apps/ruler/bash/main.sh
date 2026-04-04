#!/usr/bin/env bash
# Ruler — Bash CLI Example
#
# Demonstrates: NL to CLIPS rule generation with validation
# Subcommands: generate, validate, examples
#
# Usage:
#   bash main.sh generate "Create a rule for temperature alerts"
#   bash main.sh validate rules.clp
#   bash main.sh examples
#   bash main.sh generate "..." --verbose --step

set -euo pipefail
source "$(dirname "$0")/../../../shared/bash/nxuskit-common.sh"

# Extract subcommand before parse_args
subcommand="${1:-examples}"
shift 2>/dev/null || true
parse_args "$@"
check_prereqs

echo "=== Ruler (NL to CLIPS Generator) Demo ==="
echo

# --- CLIPS syntax validation ---
validate_clips() {
    local code="$1"
    local errors=()

    # Check balanced parentheses
    local open close
    open=$(echo "$code" | tr -cd '(' | wc -c | tr -d ' ')
    close=$(echo "$code" | tr -cd ')' | wc -c | tr -d ' ')
    if [[ "$open" -ne "$close" ]]; then
        errors+=("Unbalanced parentheses: $open open, $close close")
    fi

    # Check for required constructs
    if ! echo "$code" | grep -q "deftemplate\|defrule"; then
        errors+=("Missing deftemplate or defrule construct")
    fi

    # Check for dangerous patterns
    if echo "$code" | grep -qiE "system|exec|remove|delete-file"; then
        errors+=("Dangerous pattern detected (system/exec/remove)")
    fi

    if [[ ${#errors[@]} -gt 0 ]]; then
        echo "VALIDATION FAILED:"
        for err in "${errors[@]}"; do
            echo "  ✗ $err"
        done
        return 1
    else
        echo "VALIDATION PASSED"
        echo "  ✓ Parentheses balanced ($open pairs)"
        echo "  ✓ Required constructs present"
        echo "  ✓ No dangerous patterns"
        return 0
    fi
}

case "$subcommand" in
    generate)
        description="${REMAINING_ARGS[0]:-Create a temperature monitoring rule that triggers an alert when temperature exceeds 100 degrees}"

        step_pause "Generating CLIPS rules from description..." \
            "nxusKit CLI: call sends description to LLM" \
            "LLM generates deftemplate + defrule constructs" \
            "Output is validated for syntax correctness"

        echo "Description: $description"
        echo

        # Build request
        req_file="$(tmpfile gen-request.json)"
        jq --arg desc "$description" '.messages[1].content = $desc' \
            "$SCRIPT_DIR/requests/generate-request.json" > "$req_file"

        out_file="$(tmpfile gen-output.json)"
        if ! run_cli call --provider ollama -i "$req_file" -f json -o "$out_file"; then
            die "LLM call failed"
        fi

        clips_code=$(jq -r '.result.content' "$out_file")

        echo "Generated CLIPS Code:"
        echo "---"
        echo "$clips_code"
        echo "---"
        echo

        # Validate
        validate_clips "$clips_code"
        ;;

    validate)
        file="${REMAINING_ARGS[0]:-}"
        if [[ -z "$file" || ! -f "$file" ]]; then
            die "Usage: bash main.sh validate <file.clp>"
        fi

        echo "Validating: $file"
        echo
        code=$(cat "$file")
        validate_clips "$code"
        ;;

    examples)
        echo "Progressive Complexity Examples:"
        echo
        echo "--- Basic (deftemplate + simple defrule) ---"
        echo 'bash main.sh generate "Create a rule that classifies temperature as hot when above 30"'
        echo
        echo "--- Intermediate (multiple rules with conditions) ---"
        echo 'bash main.sh generate "Create rules for a traffic light system with red, yellow, and green states"'
        echo
        echo "--- Advanced (complex conditions, salience) ---"
        echo 'bash main.sh generate "Create an alert system with escalation: warning at 80% capacity, critical at 95%, and auto-scaling trigger at 90% with 5-minute cooldown"'
        ;;

    *)
        echo "Usage: bash main.sh <command> [args]"
        echo
        echo "Commands:"
        echo "  generate <description>  Generate CLIPS rules from natural language"
        echo "  validate <file.clp>     Validate CLIPS file syntax"
        echo "  examples                Show example descriptions"
        die "Unknown command: $subcommand" 2
        ;;
esac

echo
echo "Done."
