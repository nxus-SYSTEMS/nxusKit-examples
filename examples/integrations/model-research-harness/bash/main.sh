#!/usr/bin/env bash
# Thin Bash wrapper for the Python model research harness.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_DIR="${SCRIPT_DIR}/../python"
PYTHON_BIN="${NXUSKIT_PYTHON:-${PYTHON_BIN:-python3}}"

if [[ -n "${NXUSKIT_SDK_DIR:-}" && -d "${NXUSKIT_SDK_DIR}/python/src" ]]; then
  export PYTHONPATH="${NXUSKIT_SDK_DIR}/python/src${PYTHONPATH:+:${PYTHONPATH}}"
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  "$PYTHON_BIN" "${PY_DIR}/main.py" --help
  exit 0
fi

exec "$PYTHON_BIN" "${PY_DIR}/main.py" "$@"
