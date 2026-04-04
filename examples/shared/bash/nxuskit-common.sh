#!/usr/bin/env bash
# nxuskit-common.sh — Shared helper for nxusKit Bash CLI examples
#
# Source this file from any Bash example:
#   source "$(dirname "$0")/../../shared/bash/nxuskit-common.sh"
#
# Provides: parse_args, check_prereqs, run_cli, step_pause, die,
#           require_jq_key, tmpfile
#
# Exported variables (after parse_args):
#   VERBOSE, STEP, SCENARIO, SCRIPT_DIR, NXUSKIT_CLI

set -euo pipefail

# --- Variables (defaults) ---
VERBOSE=0
STEP=0
SCENARIO=""
SCRIPT_DIR=""
NXUSKIT_CLI="${NXUSKIT_CLI:-nxuskit-cli}"
_COMMON_TMPDIR=""

# --- Core functions ---

die() {
    local msg="${1:-Unknown error}"
    local code="${2:-1}"
    echo "ERROR: $msg" >&2
    exit "$code"
}

parse_args() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]:-$0}")" && pwd)"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --verbose|-v) VERBOSE=1; shift ;;
            --step|-s)    STEP=1; shift ;;
            --scenario)   SCENARIO="${2:-}"; shift 2 || die "Missing value for --scenario" 2 ;;
            --)           shift; break ;;
            -*)           die "Unknown option: $1" 2 ;;
            *)            break ;;
        esac
    done
    export VERBOSE STEP SCENARIO SCRIPT_DIR NXUSKIT_CLI
    REMAINING_ARGS=("$@")  # shellcheck disable=SC2034 — used by calling scripts
}

check_prereqs() {
    # Bash version
    if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
        die "Bash 4.0+ required (found ${BASH_VERSION}). On macOS: brew install bash" 2
    fi

    # nxuskit-cli
    if ! command -v "$NXUSKIT_CLI" &>/dev/null; then
        die "nxuskit-cli not found on PATH. Install from ~/.nxuskit/sdk/current/bin/" 2
    fi

    # jq
    if ! command -v jq &>/dev/null; then
        die "jq not found. Install: brew install jq (macOS) or apt install jq (Linux)" 2
    fi
}

run_cli() {
    local output_file=""
    local args=("$@")

    # Find -o/--output in args to track output file
    for ((i=0; i<${#args[@]}; i++)); do
        if [[ "${args[$i]}" == "-o" || "${args[$i]}" == "--output" ]]; then
            output_file="${args[$((i+1))]:-}"
            break
        fi
    done

    # Verbose: echo command
    if [[ $VERBOSE -eq 1 ]]; then
        echo "[CMD] $NXUSKIT_CLI ${args[*]}"
    fi

    # Add --quiet when not verbose (suppress non-essential CLI output)
    local quiet_args=()
    if [[ $VERBOSE -eq 0 ]]; then
        quiet_args=(--quiet)
    fi

    "$NXUSKIT_CLI" "${args[@]}" "${quiet_args[@]}"
    local rc=$?

    # Verbose: show output file contents
    if [[ $VERBOSE -eq 1 && -n "$output_file" && -f "$output_file" ]]; then
        echo "[RESPONSE]"
        jq '.' "$output_file" 2>/dev/null || cat "$output_file"
        echo
    fi

    return $rc
}

step_pause() {
    local title="${1:-}"
    shift
    local bullets=("$@")

    if [[ $STEP -eq 1 ]]; then
        echo
        echo "--- $title ---"
        for bullet in "${bullets[@]}"; do
            echo "  * $bullet"
        done
        read -r -p "Press Enter to continue (q to quit)... " response
        if [[ "$response" == "q" || "$response" == "Q" ]]; then
            echo "Exiting."
            exit 0
        fi
        echo
    fi
}

require_jq_key() {
    local json_file="${1:?require_jq_key: missing json_file}"
    local key="${2:?require_jq_key: missing key}"
    # Support both simple keys ("models") and jq paths (".result.models")
    local jq_path="$key"
    if [[ "$key" != .* ]]; then
        jq_path=".$key"
    fi
    if ! jq -e "$jq_path" "$json_file" &>/dev/null; then
        die "Required key '$jq_path' not found in $json_file"
    fi
}

tmpfile() {
    local name="${1:?tmpfile: missing name}"
    if [[ -z "$_COMMON_TMPDIR" ]]; then
        _COMMON_TMPDIR="${SCRIPT_DIR}/.tmp"
        mkdir -p "$_COMMON_TMPDIR"
    fi
    echo "${_COMMON_TMPDIR}/${name}"
}

# Cleanup trap
_cleanup() {
    if [[ -n "$_COMMON_TMPDIR" && -d "$_COMMON_TMPDIR" ]]; then
        rm -rf "$_COMMON_TMPDIR"
    fi
}
trap _cleanup EXIT
trap 'echo; echo "Interrupted."; exit 130' INT
