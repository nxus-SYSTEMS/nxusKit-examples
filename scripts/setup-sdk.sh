#!/usr/bin/env bash
# Configure the environment for nxusKit **extracted bundle** workflows (v0.9.4+).
#
# Usage (recommended — must *source* so exports apply to your shell):
#   source scripts/setup-sdk.sh /path/to/nxuskit-sdk-0.9.4-oss-macos-arm64.tar.gz
#   source scripts/setup-sdk.sh /path/to/nxuskit-sdk-0.9.4-oss-macos-arm64
#
# With a tarball, extracts to ./_sdk/<bundle-dir>/ at the nxusKit-examples repo root.
#
# Sets:
#   NXUSKIT_SDK_DIR   — root of the bundle (rust/, lib/, include/, docs/; v0.9.4+ often also go/, python/)
#   NXUSKIT_LIB_DIR   — $NXUSKIT_SDK_DIR/lib
#   DYLD_LIBRARY_PATH / LD_LIBRARY_PATH — so libnxuskit loads at runtime (macOS/Linux)
#   CGO_LDFLAGS / CGO_CFLAGS — for Go nxuskit-go / cgo (when building against this SDK)
#
# Prints bundle metadata when present: conformance/example-tiers.json or capability-manifest.json.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="${1:-}"

if [[ -z "$INPUT" ]]; then
  echo "usage: source scripts/setup-sdk.sh <bundle.tar.gz|extracted-bundle-root>" >&2
  [[ "${BASH_SOURCE[0]:-}" != "${0:-}" ]] && return 1
  exit 1
fi

if [[ -f "$INPUT" ]]; then
  DEST="${REPO_ROOT}/_sdk"
  rm -rf "${DEST}"
  mkdir -p "${DEST}"
  tar -xzf "$INPUT" -C "${DEST}"
  NXUSKIT_SDK_DIR="$(find "${DEST}" -maxdepth 1 -mindepth 1 -type d | head -1)"
  if [[ -z "${NXUSKIT_SDK_DIR}" ]]; then
    echo "error: extraction produced no directory under ${DEST}" >&2
    [[ "${BASH_SOURCE[0]:-}" != "${0:-}" ]] && return 1
    exit 1
  fi
else
  NXUSKIT_SDK_DIR="$(cd "$INPUT" && pwd)"
fi

export NXUSKIT_SDK_DIR
export NXUSKIT_LIB_DIR="${NXUSKIT_SDK_DIR}/lib"
export NXUSKIT_INCLUDE_DIR="${NXUSKIT_SDK_DIR}/include"

# Python cffi (`nxuskit-py`) looks for an explicit file path in NXUSKIT_LIB_PATH.
_lib_file=""
case "$(uname -s)" in
  Darwin) [[ -f "${NXUSKIT_LIB_DIR}/libnxuskit.dylib" ]] && _lib_file="${NXUSKIT_LIB_DIR}/libnxuskit.dylib" ;;
  MINGW*|MSYS*|CYGWIN*) [[ -f "${NXUSKIT_LIB_DIR}/nxuskit.dll" ]] && _lib_file="${NXUSKIT_LIB_DIR}/nxuskit.dll" ;;
  *) [[ -f "${NXUSKIT_LIB_DIR}/libnxuskit.so" ]] && _lib_file="${NXUSKIT_LIB_DIR}/libnxuskit.so" ;;
esac
if [[ -n "$_lib_file" ]]; then
  export NXUSKIT_LIB_PATH="${_lib_file}"
  echo "NXUSKIT_LIB_PATH=${NXUSKIT_LIB_PATH}"
fi

export DYLD_LIBRARY_PATH="${NXUSKIT_LIB_DIR}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export LD_LIBRARY_PATH="${NXUSKIT_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

export CGO_LDFLAGS="${CGO_LDFLAGS:-} -L${NXUSKIT_LIB_DIR} -lnxuskit"
export CGO_CFLAGS="${CGO_CFLAGS:-} -I${NXUSKIT_INCLUDE_DIR}"

if [[ -d "${NXUSKIT_SDK_DIR}/python/src" ]]; then
  export PYTHONPATH="${NXUSKIT_SDK_DIR}/python/src${PYTHONPATH:+:${PYTHONPATH}}"
  echo "PYTHONPATH includes ${NXUSKIT_SDK_DIR}/python/src"
fi

echo "NXUSKIT_SDK_DIR=${NXUSKIT_SDK_DIR}"
echo "NXUSKIT_LIB_DIR=${NXUSKIT_LIB_DIR}"

if [[ ! -f "${NXUSKIT_SDK_DIR}/rust/Cargo.toml" ]]; then
  echo "warning: expected ${NXUSKIT_SDK_DIR}/rust/Cargo.toml (nxuskit crate) — is this a full v0.9.4+ bundle?" >&2
fi

if [[ -f "${NXUSKIT_SDK_DIR}/conformance/example-tiers.json" ]]; then
  ver=""
  if command -v jq >/dev/null 2>&1; then
    ver="$(jq -r '.version // empty' "${NXUSKIT_SDK_DIR}/conformance/example-tiers.json")"
  fi
  echo "example-tiers.json present${ver:+ (version $ver)}"
elif [[ -f "${NXUSKIT_SDK_DIR}/capability-manifest.json" ]]; then
  echo "capability-manifest.json present (legacy bundle layout)"
else
  echo "note: no conformance/example-tiers.json at bundle root"
fi
