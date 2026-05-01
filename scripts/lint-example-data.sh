#!/usr/bin/env bash
# lint-example-data.sh — Validate JSON and CSV data files in examples/
#
# JSON: Must be pretty-printed with sorted keys (jq --sort-keys)
# CSV:  Must be sorted by primary key column, header row, UTF-8 LF
#
# Usage: scripts/lint-example-data.sh [--fix]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXAMPLES_DIR="${REPO_ROOT}/examples"

FIX=false
if [[ "${1:-}" == "--fix" ]]; then
    FIX=true
fi

errors=0

# ── JSON lint ────────────────────────────────────────────────────────

if ! command -v jq &>/dev/null; then
    echo "ERROR: jq is required but not installed. Install via: brew install jq" >&2
    exit 1
fi

echo "Checking JSON files in examples/..."
while IFS= read -r -d '' jsonfile; do
    # Skip node_modules, bin directories, Cargo.lock, etc.
    if [[ "$jsonfile" == *node_modules* ]] || [[ "$jsonfile" == */bin/* ]] || [[ "$jsonfile" == */target/* ]] || [[ "$jsonfile" == */.tmp/* ]]; then
        continue
    fi

    # Check sorted-key pretty-printed format
    expected=$(jq --sort-keys '.' "$jsonfile" 2>/dev/null) || {
        echo "  FAIL: $jsonfile — invalid JSON"
        errors=$((errors + 1))
        continue
    }
    actual=$(cat "$jsonfile")

    if [[ "$expected" != "$actual" ]]; then
        if $FIX; then
            echo "$expected" > "$jsonfile"
            echo "  FIXED: $jsonfile"
        else
            echo "  FAIL: $jsonfile — not sorted-key pretty-printed (run with --fix to auto-fix)"
            errors=$((errors + 1))
        fi
    fi
done < <(find "$EXAMPLES_DIR" -name '*.json' -type f -print0 2>/dev/null)

# ── CSV lint ─────────────────────────────────────────────────────────

echo "Checking CSV files in examples/..."
while IFS= read -r -d '' csvfile; do
    # Check for CRLF line endings
    if grep -Pq '\r\n' "$csvfile" 2>/dev/null; then
        if $FIX; then
            sed -i '' 's/\r$//' "$csvfile" 2>/dev/null || sed -i 's/\r$//' "$csvfile"
            echo "  FIXED: $csvfile — converted CRLF to LF"
        else
            echo "  FAIL: $csvfile — contains CRLF line endings (must be LF)"
            errors=$((errors + 1))
        fi
    fi

    # Check header row exists (first line should not be purely numeric)
    header=$(head -1 "$csvfile")
    if [[ -z "$header" ]]; then
        echo "  FAIL: $csvfile — empty file (must have header row)"
        errors=$((errors + 1))
        continue
    fi

    # Check sorted by primary key (first column), skipping header
    body=$(tail -n +2 "$csvfile")
    if [[ -n "$body" ]]; then
        sorted=$(echo "$body" | sort -t',' -k1,1)
        if [[ "$body" != "$sorted" ]]; then
            if $FIX; then
                echo "$header" > "$csvfile.tmp"
                echo "$sorted" >> "$csvfile.tmp"
                mv "$csvfile.tmp" "$csvfile"
                echo "  FIXED: $csvfile — sorted by primary key"
            else
                echo "  FAIL: $csvfile — not sorted by primary key column (run with --fix to auto-fix)"
                errors=$((errors + 1))
            fi
        fi
    fi

    # Check trailing newline
    if [[ -n "$(tail -c 1 "$csvfile")" ]]; then
        if $FIX; then
            echo "" >> "$csvfile"
            echo "  FIXED: $csvfile — added trailing newline"
        else
            echo "  FAIL: $csvfile — missing trailing newline"
            errors=$((errors + 1))
        fi
    fi
done < <(find "$EXAMPLES_DIR" -name '*.csv' -type f -print0 2>/dev/null)

# ── Summary ──────────────────────────────────────────────────────────

echo ""
if [[ $errors -eq 0 ]]; then
    echo "All example data files pass lint checks."
    exit 0
else
    echo "FAILED: $errors lint error(s) found."
    exit 1
fi
