#!/usr/bin/env bash
# Local PR readiness checks — mirrors CI jobs that don't require SDK or remote deps.
#
# Runs the same linting, formatting, and conformance checks that CI enforces,
# so issues are caught before pushing.
#
# Usage:
#   ./scripts/pre-pr-check.sh          # run all checks
#   ./scripts/pre-pr-check.sh --fix    # auto-fix formatting issues, then check
#
# Prerequisites:
#   rustfmt, ruff (pip install ruff), tokei (brew install tokei), jq, python3
#
# Exit codes:
#   0 — all checks pass
#   1 — one or more checks failed (see output for details)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

FIX_MODE=false
if [[ "${1:-}" == "--fix" ]]; then
  FIX_MODE=true
fi

FAILED=()
SKIPPED=()

# ── Helpers ───────────────────────────────────────────────────────

run_check() {
  local name="$1"
  shift
  printf "  %-40s " "$name"
  if "$@" >/dev/null 2>&1; then
    echo "✓"
  else
    echo "✗"
    FAILED+=("$name")
  fi
}

skip_check() {
  local name="$1"
  local reason="$2"
  printf "  %-40s %s\n" "$name" "– skipped ($reason)"
  SKIPPED+=("$name")
}

echo "Pre-PR checks"
echo "─────────────────────────────────────────────────────"

# ── 1. Rust formatting ───────────────────────────────────────────

if command -v rustfmt &>/dev/null; then
  RS_FILES=()
  while IFS= read -r -d '' f; do
    RS_FILES+=("$f")
  done < <(find examples \( -path '*/target/*' -o -path '*/.git/*' \) -prune -o -name '*.rs' ! -path '*/riffer/shared/testdata/generate_fixtures.rs' -print0)

  if [ ${#RS_FILES[@]} -gt 0 ]; then
    if $FIX_MODE; then
      rustfmt --edition 2024 "${RS_FILES[@]}" 2>/dev/null || true
    fi
    run_check "Format (Rust)" rustfmt --edition 2024 --check "${RS_FILES[@]}"
  else
    skip_check "Format (Rust)" "no .rs files"
  fi
else
  skip_check "Format (Rust)" "rustfmt not installed"
fi

# ── 2. Python lint + format ──────────────────────────────────────

if command -v ruff &>/dev/null; then
  PY_FILES=$(find examples -name "*.py" 2>/dev/null || true)
  if [ -n "$PY_FILES" ]; then
    if $FIX_MODE; then
      ruff format examples/ 2>/dev/null || true
      ruff check --fix examples/ 2>/dev/null || true
    fi
    run_check "Lint (Python — ruff check)" ruff check examples/
    run_check "Format (Python — ruff format)" ruff format --check examples/
  else
    skip_check "Lint (Python)" "no .py files"
  fi
else
  skip_check "Lint (Python)" "ruff not installed (pip install ruff)"
fi

# ── 3. Go formatting ─────────────────────────────────────────────

if command -v gofmt &>/dev/null; then
  GO_FILES=$(find examples -name '*.go' -not -path '*/vendor/*' 2>/dev/null || true)
  if [ -n "$GO_FILES" ]; then
    check_gofmt() {
      local unformatted
      unformatted=$(gofmt -l $GO_FILES 2>/dev/null)
      [ -z "$unformatted" ]
    }
    if $FIX_MODE; then
      gofmt -w $GO_FILES 2>/dev/null || true
    fi
    run_check "Format (Go)" check_gofmt
  else
    skip_check "Format (Go)" "no .go files"
  fi
else
  skip_check "Format (Go)" "gofmt not installed"
fi

# ── 4. Content staleness ─────────────────────────────────────────

if command -v tokei &>/dev/null && [ -f scripts/check-content-staleness.sh ]; then
  run_check "Content staleness" scripts/check-content-staleness.sh
else
  skip_check "Content staleness" "tokei not installed (brew install tokei)"
fi

# ── 5. Difficulty drift ──────────────────────────────────────────

if [ -f scripts/check-difficulty-drift.sh ] && command -v tokei &>/dev/null; then
  run_check "Difficulty drift" scripts/check-difficulty-drift.sh
else
  skip_check "Difficulty drift" "tokei or scoring tools missing"
fi

# ── 6. Example tier manifest ─────────────────────────────────────

if [ -f scripts/verify-example-tier-manifest.sh ]; then
  run_check "Example tier manifest" scripts/verify-example-tier-manifest.sh
else
  skip_check "Example tier manifest" "script missing"
fi

# ── 7. Examples manifest directory parity ─────────────────────────

if [ -f tools/scripts/verify_examples_manifest.sh ]; then
  run_check "Examples manifest parity" tools/scripts/verify_examples_manifest.sh
else
  skip_check "Examples manifest parity" "script missing"
fi

# ── 8. Launch helper scripts (syntax) ────────────────────────────

check_bash_syntax() {
  local fail=0
  for f in scripts/setup-sdk.sh scripts/test-examples.sh scripts/test-entitlements.sh scripts/check-rust-example-linkage.sh; do
    [ -f "$f" ] && bash -n "$f" || fail=1
  done
  return $fail
}
run_check "Bash syntax (helper scripts)" check_bash_syntax

# ── 9. Leak gate (forbidden terms) ───────────────────────────────

check_leak_gate() {
  local FORBIDDEN_TERMS=(
    "INTERNAL-ONLY"
    "nxusKit-internal"
    "nxusKit-examples-internal"
    "nxusKit-plugins-internal"
    "ai-artifacts"
  )
  local SCAN_PATHS=()
  for d in examples conformance scripts tools; do
    [[ -d "$d" ]] && SCAN_PATHS+=("$d")
  done
  for f in README.md SECURITY.md CODE_OF_CONDUCT.md; do
    [[ -f "$f" ]] && SCAN_PATHS+=("$f")
  done

  for term in "${FORBIDDEN_TERMS[@]}"; do
    local hits
    hits=$(grep -r -n \
      --include='*.md' --include='*.go' --include='*.rs' \
      --include='*.py' --include='*.json' --include='*.yaml' \
      --include='*.yml' --include='*.sh' \
      "$term" "${SCAN_PATHS[@]}" 2>/dev/null \
    | grep -v "sync-example-tiers-from-sdk\.sh" \
    | grep -v "pre-pr-check\.sh" || true)
    if [[ -n "$hits" ]]; then
      return 1
    fi
  done
  return 0
}
run_check "Leak gate (internal refs)" check_leak_gate

# ── 10. Stray binaries ───────────────────────────────────────────

check_stray_binaries() {
  local stray
  stray=$(find examples -type f -perm /111 \
    ! -name "*.sh" ! -name "Makefile" ! -name "*.py" \
    ! -path "*/bin/*" ! -path "*/.git/*" 2>/dev/null || true)
  [ -z "$stray" ]
}
run_check "Stray binary check" check_stray_binaries

# ── Summary ───────────────────────────────────────────────────────

echo "─────────────────────────────────────────────────────"

if [ ${#FAILED[@]} -gt 0 ]; then
  echo ""
  echo "FAILED (${#FAILED[@]}):"
  for f in "${FAILED[@]}"; do
    echo "  ✗ $f"
  done
  if ! $FIX_MODE; then
    echo ""
    echo "Tip: run with --fix to auto-format before checking."
  fi
  exit 1
else
  echo "All checks passed."
  exit 0
fi
