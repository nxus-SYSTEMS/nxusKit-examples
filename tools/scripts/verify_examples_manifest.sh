#!/usr/bin/env bash
set -eu -o pipefail

# tools/scripts/verify_examples_manifest.sh
# Ensures required examples exist for all listed languages and remain in parity.
#
# Manifest format (v2.0.0):
#   Each example has "name", "required" (bool), and "implementations" (map of
#   lang → directory path relative to repo root).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="${ROOT_DIR}/conformance/examples_manifest.json"

echo "Verifying examples manifest parity..."
echo "  Manifest: ${MANIFEST}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "ERROR: Missing examples manifest at ${MANIFEST}" >&2
  exit 1
fi

require_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required for verify_examples_manifest.sh" >&2
    echo "Install with: brew install jq (macOS) or apt-get install jq (Linux)" >&2
    exit 1
  fi
}
require_jq

echo ""

missing=0
checked=0
skipped=0

# Iterate over each example in the manifest
EXAMPLE_COUNT=$(jq '.examples | length' "${MANIFEST}")

for i in $(seq 0 $((EXAMPLE_COUNT - 1))); do
  name=$(jq -r ".examples[$i].name" "${MANIFEST}")
  required=$(jq -r ".examples[$i].required" "${MANIFEST}")

  if [[ "$required" != "true" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  # Get all language implementations for this example
  langs=$(jq -r ".examples[$i].implementations | keys[]" "${MANIFEST}")

  for lang in ${langs}; do
    impl_path=$(jq -r ".examples[$i].implementations[\"${lang}\"]" "${MANIFEST}")
    full_path="${ROOT_DIR}/${impl_path}"
    checked=$((checked + 1))

    if [[ -d "$full_path" ]]; then
      echo "  OK: ${name} (${lang})"
    else
      echo "  ERROR: ${name} (${lang}) missing at ${impl_path}" >&2
      missing=$((missing + 1))
    fi
  done

  frontend_count=$(jq "(.examples[$i].frontends // []) | length" "${MANIFEST}")
  if [[ "${frontend_count}" -gt 0 ]]; then
    for frontend_index in $(seq 0 $((frontend_count - 1))); do
      frontend_language=$(jq -r ".examples[$i].frontends[$frontend_index].language" "${MANIFEST}")
      frontend_id=$(jq -r ".examples[$i].frontends[$frontend_index].id" "${MANIFEST}")
      entrypoint=$(jq -r ".examples[$i].frontends[$frontend_index].entrypoint" "${MANIFEST}")
      documentation=$(jq -r ".examples[$i].frontends[$frontend_index].documentation" "${MANIFEST}")

      checked=$((checked + 1))
      if ! jq -e --arg language "${frontend_language}" ".examples[$i].implementations | has(\$language)" "${MANIFEST}" >/dev/null; then
        echo "  ERROR: ${name} frontend ${frontend_id} language ${frontend_language} has no canonical implementation" >&2
        missing=$((missing + 1))
      elif [[ ! -f "${ROOT_DIR}/${entrypoint}" ]]; then
        echo "  ERROR: ${name} frontend ${frontend_id} missing entrypoint at ${entrypoint}" >&2
        missing=$((missing + 1))
      elif [[ ! -f "${ROOT_DIR}/${documentation}" ]]; then
        echo "  ERROR: ${name} frontend ${frontend_id} missing documentation at ${documentation}" >&2
        missing=$((missing + 1))
      else
        echo "  OK: ${name} frontend (${frontend_id})"
      fi
    done
  fi
done

echo ""
echo "Checked: ${checked} implementations across $((EXAMPLE_COUNT - skipped)) required examples (${skipped} optional skipped)"

if [[ "${missing}" -ne 0 ]]; then
  echo "ERROR: ${missing} implementation(s) missing — parity check failed." >&2
  exit 1
fi

echo "Examples parity check passed."
