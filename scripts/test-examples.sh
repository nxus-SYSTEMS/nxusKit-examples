#!/usr/bin/env bash
# Build (and optionally test / dry-run / smoke-run) nxusKit-examples against an **installed SDK tree** only
# (`--sdk-dir` or `--tarball` extract). Go `replace` and Rust `nxuskit` path deps are rewritten to
# **`$NXUSKIT_SDK_DIR/{go,rust,python}`** — never to a separate monorepo checkout.
#
# Usage:
#   scripts/test-examples.sh --sdk-dir "$NXUSKIT_SDK_DIR" --lang rust [--tier all|community|pro] [--release] [--test] [--dry-run] [--json]
#   scripts/test-examples.sh --tarball nxuskit-sdk-0.9.1-oss-macos-arm64.tar.gz --lang rust --build-only
#
#   --smoke-run            After successful builds, run each matrix entry (conformance/example_smoke_matrix.json).
#                          Pro-tier rows with entitlement_probe: run **without** token/env (expect failure + license
#                          hint in output), then **with** restored token (expect success). If no token exists, the
#                          second half is skipped unless SMOKE_REQUIRE_PRO_LICENSE=1 (then fail).
#
# Tier filter: examples_manifest.json supplies Rust/Go/Python paths when tier != all or when using
# manifest-backed langs. Rust tier "all" = every Cargo.toml under examples/ (except shared/).
#
# --json writes a JSON array to stdout at the end (and still prints human progress to stderr).
#
# macOS Apple Silicon: use a Pro or OSS bundle for `NXUSKIT_SDK_DIR`; for cloud LLM examples set API keys
# (e.g. `set -a && source ../peeler/.env && set +a` before invoking). SMOKE_SKIP_CLOUD_LLM=1 skips rows that
# need Anthropic/OpenAI for a full run.
# LM Studio: SMOKE_INCLUDE_LOCAL_LMSTUDIO=1 to run those smokes.
# Go rows that need Ollama: auto-run if GET $OLLAMA_HOST/api/tags succeeds (default http://127.0.0.1:11434); use
# SMOKE_SKIP_LOCAL_OLLAMA=1 to skip, or SMOKE_INCLUDE_LOCAL_OLLAMA=1 to run even when the probe fails.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${REPO_ROOT}/conformance/examples_manifest.json"
SDK_DIR=""
TARBALL=""
LANG=""
TIER="all"
BUILD_ONLY=0
RELEASE=0
RUN_TESTS=0
DRY_RUN=0
JSON_OUT=0
SMOKE_RUN=0
SMOKE_MATRIX="${REPO_ROOT}/conformance/example_smoke_matrix.json"
JSONL="${REPO_ROOT}/.test-examples-results.jsonl"
rm -f "${JSONL}"

usage() {
  cat <<'EOF' >&2
usage: test-examples.sh --sdk-dir <path> --lang rust|go|python|bash|all [options]
       test-examples.sh --tarball <file.tar.gz> --lang <same> [options]

Options:
  --tier all|community|pro   Filter by examples_manifest tier (default all). Rust "all" = all Cargo workspaces.
  --build-only               Skip tests and dry-run (exit after builds).
  --release                  cargo build --release (Rust only).
  --test                     cargo test / go test -short after successful builds (where applicable).
  --dry-run                  python: python3 main.py --help (needs bundle lib + SDK python/ with pyproject.toml).
  --smoke-run                Run example smoke matrix after builds (see header).
  --smoke-matrix PATH        JSON matrix (default: conformance/example_smoke_matrix.json).
  --json                     Emit JSON summary to stdout at end.

Requires: jq when using --tier other than all with Rust-only builds, --lang go|python|all, --json, --dry-run, or --smoke-run.
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sdk-dir) SDK_DIR="$2"; shift 2 ;;
    --tarball)
      TARBALL="$2"
      shift 2
      TMP="${REPO_ROOT}/_sdk"
      rm -rf "${TMP}"
      mkdir -p "${TMP}"
      tar -xzf "$TARBALL" -C "${TMP}"
      SDK_DIR="$(find "${TMP}" -maxdepth 1 -mindepth 1 -type d | head -1)"
      ;;
    --lang) LANG="$2"; shift 2 ;;
    --tier) TIER="$2"; shift 2 ;;
    --build-only) BUILD_ONLY=1; shift ;;
    --release) RELEASE=1; shift ;;
    --test) RUN_TESTS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --json) JSON_OUT=1; shift ;;
    --smoke-run) SMOKE_RUN=1; shift ;;
    --smoke-matrix) SMOKE_MATRIX="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

[[ -n "$LANG" ]] || usage
[[ -n "$SDK_DIR" ]] || usage

NEED_JQ=0
[[ "$TIER" != "all" ]] && NEED_JQ=1
[[ "$LANG" == "python" || "$LANG" == "go" || "$LANG" == "all" ]] && NEED_JQ=1
[[ "$JSON_OUT" -eq 1 || "$DRY_RUN" -eq 1 || "$SMOKE_RUN" -eq 1 ]] && NEED_JQ=1
if [[ "$NEED_JQ" -eq 1 ]] && ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required for this flag combination (--tier, --lang python|go|all, --json, --dry-run, --smoke-run)" >&2
  exit 1
fi

export NXUSKIT_SDK_DIR="$(cd "$SDK_DIR" && pwd)"
export NXUSKIT_LIB_DIR="${NXUSKIT_SDK_DIR}/lib"
export DYLD_LIBRARY_PATH="${NXUSKIT_LIB_DIR}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
export LD_LIBRARY_PATH="${NXUSKIT_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export CGO_LDFLAGS="${CGO_LDFLAGS:-} -L${NXUSKIT_LIB_DIR} -lnxuskit"
export CGO_CFLAGS="${CGO_CFLAGS:-} -I${NXUSKIT_SDK_DIR}/include"

_nx_py_lib=""
case "$(uname -s)" in
  Darwin) [[ -f "${NXUSKIT_LIB_DIR}/libnxuskit.dylib" ]] && _nx_py_lib="${NXUSKIT_LIB_DIR}/libnxuskit.dylib" ;;
  MINGW*|MSYS*|CYGWIN*) [[ -f "${NXUSKIT_LIB_DIR}/nxuskit.dll" ]] && _nx_py_lib="${NXUSKIT_LIB_DIR}/nxuskit.dll" ;;
  *) [[ -f "${NXUSKIT_LIB_DIR}/libnxuskit.so" ]] && _nx_py_lib="${NXUSKIT_LIB_DIR}/libnxuskit.so" ;;
esac
[[ -n "$_nx_py_lib" ]] && export NXUSKIT_LIB_PATH="${_nx_py_lib}"

RUST_NXUSKIT_PATH=""
if [[ -f "${NXUSKIT_SDK_DIR}/rust/Cargo.toml" ]]; then
  RUST_NXUSKIT_PATH="$(cd "${NXUSKIT_SDK_DIR}/rust" && pwd)"
elif [[ -f "${NXUSKIT_SDK_DIR}/packages/nxuskit/Cargo.toml" ]]; then
  RUST_NXUSKIT_PATH="$(cd "${NXUSKIT_SDK_DIR}/packages/nxuskit" && pwd)"
else
  echo "error: no nxuskit Rust crate under SDK (expected \$NXUSKIT_SDK_DIR/rust/ or .../packages/nxuskit/)" >&2
  exit 1
fi

# nxuskit-go module root for go mod replace (bundled SDK go/ only).
NXUSKIT_GO_MOD_ROOT=""
if [[ -f "${NXUSKIT_SDK_DIR}/go/go.mod" ]] && [[ -d "${NXUSKIT_SDK_DIR}/go/internal/ffi" ]]; then
  NXUSKIT_GO_MOD_ROOT="$(cd "${NXUSKIT_SDK_DIR}/go" && pwd)"
fi

# nxuskit-py root: bundled SDK python/ only.
PYTHON_SDK_ROOT=""
if [[ -f "${NXUSKIT_SDK_DIR}/python/pyproject.toml" ]]; then
  PYTHON_SDK_ROOT="${NXUSKIT_SDK_DIR}/python"
fi

emit_jsonl() {
  local example="$1" language="$2" phase="$3" status="$4" ms="$5" detail="${6:-}"
  [[ "$JSON_OUT" -eq 1 ]] || return 0
  jq -nc --arg ex "$example" --arg lg "$language" --arg ph "$phase" --arg st "$status" \
    --argjson ms "$ms" --arg dt "$detail" \
    '{example:$ex, lang:$lg, phase:$ph, status:$st, ms:$ms, detail:$dt}' >>"${JSONL}"
}

SMOKE_LICENSE_ERR_RE="${SMOKE_LICENSE_ERR_RE:-license|entitlement|subscription|not entitled|Pro required|trial}"

smoke_ollama_base_url() {
  local h="${OLLAMA_HOST:-127.0.0.1:11434}"
  if [[ "$h" != http://* && "$h" != https://* ]]; then
    h="http://${h}"
  fi
  h="${h%/}"
  printf '%s' "$h"
}

smoke_ollama_reachable() {
  command -v curl >/dev/null 2>&1 || return 1
  curl -sf --max-time 2 "$(smoke_ollama_base_url)/api/tags" >/dev/null 2>&1
}

smoke_restore_license_token_file() {
  local saved="$1"
  local tok="${ENT_TOKEN_FILE:-$HOME/.nxuskit/license.token}"
  if [[ -n "$saved" ]]; then
    mkdir -p "$(dirname "$tok")"
    mv "$saved" "$tok"
  else
    rm -f "$tok"
  fi
}

smoke_run_entitlement_pair() {
  local id="$1" lang="$2" dir="$3"
  shift 3
  local -a cmd=("$@")
  local tok="${ENT_TOKEN_FILE:-$HOME/.nxuskit/license.token}"
  local saved_file="" saved_env="${NXUSKIT_LICENSE_TOKEN-}"
  local start elapsed outf st combined

  if [[ -f "$tok" ]]; then
    saved_file="$(mktemp)"
    cp "$tok" "$saved_file"
  fi
  rm -f "$tok"
  export NXUSKIT_LICENSE_TOKEN=""

  outf="$(mktemp)"
  start="$(_ms)"
  set +e
  (cd "$dir" && "${cmd[@]}") </dev/null >"$outf" 2>&1
  st=$?
  set -e
  elapsed=$(( $(_ms) - start ))
  combined="$(cat "$outf")"
  rm -f "$outf"

  if [[ "$st" -eq 0 ]]; then
    smoke_restore_license_token_file "$saved_file"
    export NXUSKIT_LICENSE_TOKEN="${saved_env}"
    echo "error: smoke entitlement (no license) expected non-zero exit for $id, got 0" >&2
    emit_jsonl "$id" "$lang" "smoke-ent-no-lic" fail "$elapsed" "expected failure"
    return 1
  fi
  if ! grep -qiE "$SMOKE_LICENSE_ERR_RE" <<<"$combined"; then
    smoke_restore_license_token_file "$saved_file"
    export NXUSKIT_LICENSE_TOKEN="${saved_env}"
    echo "error: smoke entitlement (no license) stderr did not match /$SMOKE_LICENSE_ERR_RE/ for $id" >&2
    printf '%s\n' "$combined" >&2
    emit_jsonl "$id" "$lang" "smoke-ent-no-lic" fail "$elapsed" "stderr pattern"
    return 1
  fi
  emit_jsonl "$id" "$lang" "smoke-ent-no-lic" ok "$elapsed" ""

  smoke_restore_license_token_file "$saved_file"
  export NXUSKIT_LICENSE_TOKEN="${saved_env}"

  if [[ -n "$saved_file" || -n "$saved_env" ]]; then
    start="$(_ms)"
    set +e
    (cd "$dir" && "${cmd[@]}") </dev/null >/dev/null 2>&1
    st=$?
    set -e
    elapsed=$(( $(_ms) - start ))
    if [[ "$st" -ne 0 ]]; then
      echo "error: smoke entitlement (with license) expected 0 for $id, got $st" >&2
      emit_jsonl "$id" "$lang" "smoke-ent-lic" fail "$elapsed" "exit $st"
      return 1
    fi
    echo "OK smoke entitlement pair: $id" >&2
    emit_jsonl "$id" "$lang" "smoke-ent-lic" ok "$elapsed" ""
  else
    if [[ "${SMOKE_REQUIRE_PRO_LICENSE:-}" == "1" ]]; then
      echo "error: smoke entitlement with-license skipped but SMOKE_REQUIRE_PRO_LICENSE=1 ($id)" >&2
      return 1
    fi
    echo "skip: smoke with-license ($id): no license file or NXUSKIT_LICENSE_TOKEN" >&2
    emit_jsonl "$id" "$lang" "smoke-ent-lic" ok "0" "skipped no token"
  fi
  return 0
}

smoke_run_row() {
  local row="$1"
  local id dir lang cloud probe start elapsed st
  id="$(jq -r '.id' <<<"$row")"
  dir="${REPO_ROOT}/$(jq -r '.cwd_rel' <<<"$row")"
  lang="$(jq -r '.language' <<<"$row")"
  cloud="$(jq -r '.requires_cloud_llm' <<<"$row")"
  probe="$(jq -r '.entitlement_probe' <<<"$row")"
  local -a cmd=()
  while IFS= read -r part; do cmd+=("$part"); done < <(jq -r '.command[]' <<<"$row")
  if [[ "$RELEASE" -eq 1 && "${cmd[0]:-}" == "cargo" && "${cmd[1]:-}" == "run" ]]; then
    local -a cr=(cargo run --release)
    local i=2
    for ((; i<${#cmd[@]}; i++)); do cr+=("${cmd[i]}"); done
    cmd=("${cr[@]}")
  fi

  if [[ "$cloud" == "true" ]]; then
    if [[ "${SMOKE_SKIP_CLOUD_LLM:-}" == "1" ]]; then
      echo "skip smoke (SMOKE_SKIP_CLOUD_LLM): $id" >&2
      return 0
    fi
    if [[ -z "${ANTHROPIC_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
      echo "skip smoke (no ANTHROPIC_API_KEY or OPENAI_API_KEY): $id" >&2
      return 0
    fi
  fi

  local needs_lmstudio
  needs_lmstudio="$(jq -r '.requires_local_lmstudio // false' <<<"$row")"
  if [[ "$needs_lmstudio" == "true" ]] && [[ -z "${SMOKE_INCLUDE_LOCAL_LMSTUDIO:-}" ]]; then
    echo "skip smoke (LM Studio; SMOKE_INCLUDE_LOCAL_LMSTUDIO=1): $id" >&2
    return 0
  fi

  local needs_ollama_go obase
  needs_ollama_go="$(jq -r '.requires_local_ollama_go // false' <<<"$row")"
  if [[ "$needs_ollama_go" == "true" ]]; then
    if [[ "${SMOKE_SKIP_LOCAL_OLLAMA:-}" == "1" ]]; then
      echo "skip smoke (SMOKE_SKIP_LOCAL_OLLAMA): $id" >&2
      return 0
    fi
    if [[ -z "${SMOKE_INCLUDE_LOCAL_OLLAMA:-}" ]] && ! smoke_ollama_reachable; then
      obase="$(smoke_ollama_base_url)"
      echo "skip smoke (Ollama not reachable at ${obase}; SMOKE_INCLUDE_LOCAL_OLLAMA=1 to force): $id" >&2
      return 0
    fi
  fi

  if [[ "$probe" == "true" ]]; then
    smoke_run_entitlement_pair "$id" "$lang" "$dir" "${cmd[@]}" || return 1
    return 0
  fi

  start="$(_ms)"
  set +e
  (cd "$dir" && "${cmd[@]}") </dev/null >/dev/null 2>&1
  st=$?
  set -e
  elapsed=$(( $(_ms) - start ))
  if [[ "$st" -ne 0 ]]; then
    echo "error: smoke run failed ($st): $id in $dir" >&2
    emit_jsonl "$id" "$lang" smoke fail "$elapsed" "exit $st"
    return 1
  fi
  echo "OK smoke: $id" >&2
  emit_jsonl "$id" "$lang" smoke ok "$elapsed" ""
  return 0
}

smoke_lang() {
  local lg="$1" failed="" row
  if [[ ! -f "$SMOKE_MATRIX" ]]; then
    echo "error: smoke matrix not found: $SMOKE_MATRIX" >&2
    return 1
  fi
  if [[ "$lg" == "go" ]] && [[ -z "$NXUSKIT_GO_MOD_ROOT" ]]; then
    echo "skip: smoke go (need SDK go/ with internal/ffi under \$NXUSKIT_SDK_DIR)" >&2
    return 0
  fi
  if [[ "$lg" == "python" ]] && { [[ -z "$PYTHON_SDK_ROOT" ]] || [[ ! -f "${PYTHON_SDK_ROOT}/pyproject.toml" ]]; }; then
    echo "skip: smoke python (need SDK python/pyproject.toml under \$NXUSKIT_SDK_DIR)" >&2
    return 0
  fi
  if [[ "$lg" == "python" ]] && [[ -z "${NXUSKIT_LIB_PATH:-}" ]]; then
    echo "error: smoke python needs NXUSKIT_LIB_PATH / bundle lib" >&2
    return 1
  fi
  if [[ "$lg" == "python" ]]; then
    local py_root
    py_root="$(cd "${PYTHON_SDK_ROOT}" && pwd)"
    export PYTHONPATH="${py_root}/src:${PYTHONPATH:-}"
  fi

  while IFS= read -r row; do
    smoke_run_row "$row" || failed="$failed $(jq -r '.id' <<<"$row")"
  done < <(jq -c --arg lg "$lg" --arg t "$TIER" '
    .runs[]
    | select(.language == $lg)
    | select($t == "all" or .tier == $t)
  ' "${SMOKE_MATRIX}")

  if [[ -n "$failed" ]]; then
    echo "error: smoke failures:$failed" >&2
    return 1
  fi
}

smoke_all() {
  case "$LANG" in
    rust) smoke_lang rust ;;
    go)   smoke_lang go ;;
    python) smoke_lang python ;;
    all)
      smoke_lang rust || return 1
      smoke_lang go || return 1
      smoke_lang python || return 1
      ;;
    *) return 0 ;;
  esac
}

BACKUPS=()
restore_tomls() {
  for b in "${BACKUPS[@]}"; do
    orig="${b%.bak}"
    mv "$b" "$orig"
  done
}
trap restore_tomls EXIT

patch_rust_tomls() {
  echo "== Rust: nxuskit path -> ${RUST_NXUSKIT_PATH}" >&2
  while IFS= read -r toml; do
    if grep -q 'path.*packages/nxuskit' "$toml"; then
      cp "$toml" "${toml}.bak"
      BACKUPS+=("${toml}.bak")
      if sed --version >/dev/null 2>&1; then
        sed -i "s|path = \"[^\"]*packages/nxuskit\"|path = \"${RUST_NXUSKIT_PATH}\"|g" "$toml"
      else
        sed -i '' "s|path = \"[^\"]*packages/nxuskit\"|path = \"${RUST_NXUSKIT_PATH}\"|g" "$toml"
      fi
    fi
  done < <(find "${REPO_ROOT}/examples" -name Cargo.toml)
}

rust_dirs_all() {
  find "${REPO_ROOT}/examples" -name Cargo.toml -exec dirname {} \;
}

rust_dirs_tiered() {
  jq -r --arg t "$TIER" '
    .examples[]
    | select($t == "all" or .tier == $t)
    | .implementations.rust // empty
    | select(length > 0)
  ' "${MANIFEST}" | while read -r rel; do
    echo "${REPO_ROOT}/${rel}"
  done
}

_ms() { python3 -c 'import time; print(int(time.time()*1000))' 2>/dev/null || echo 0; }

rust_build_one() {
  local dir="$1"
  local name="${dir#$REPO_ROOT/}"
  local start elapsed
  start="$(_ms)"
  local cargo_args=(build)
  [[ "$RELEASE" -eq 1 ]] && cargo_args=(build --release)
  if (cd "$dir" && cargo "${cargo_args[@]}"); then
    elapsed=$(( $(_ms) - start ))
    echo "OK rust build: $dir" >&2
    emit_jsonl "$name" rust build ok "$elapsed" ""
    if [[ "$RUN_TESTS" -eq 1 && "$BUILD_ONLY" -eq 0 ]]; then
      start="$(_ms)"
      if (cd "$dir" && cargo test -q); then
        elapsed=$(( $(_ms) - start ))
        emit_jsonl "$name" rust test ok "$elapsed" ""
      else
        elapsed=$(( $(_ms) - start ))
        emit_jsonl "$name" rust test fail "$elapsed" "cargo test"
        return 1
      fi
    fi
  else
    elapsed=$(( $(_ms) - start ))
    emit_jsonl "$name" rust build fail "$elapsed" "cargo build"
    return 1
  fi
}

rust_build() {
  patch_rust_tomls
  local failed="" d
  if [[ "$TIER" == "all" ]]; then
    while IFS= read -r dir; do
      echo "$dir" | grep -q "shared/" && continue
      rust_build_one "$dir" || failed="$failed $dir"
    done < <(rust_dirs_all)
  else
    while IFS= read -r dir; do
      [[ -f "$dir/Cargo.toml" ]] || continue
      rust_build_one "$dir" || failed="$failed $dir"
    done < <(rust_dirs_tiered)
  fi
  if [[ -n "$failed" ]]; then
    echo "error: Rust build/test failures:$failed" >&2
    return 1
  fi
}

go_dirs_tiered() {
  jq -r --arg t "$TIER" '
    .examples[]
    | select($t == "all" or .tier == $t)
    | .implementations.go // empty
    | select(length > 0)
  ' "${MANIFEST}" | while read -r rel; do
    echo "${REPO_ROOT}/${rel}"
  done
}

go_build() {
  if [[ -z "$NXUSKIT_GO_MOD_ROOT" ]]; then
    echo "skip: Go needs SDK go/ (go.mod + internal/ffi) under \$NXUSKIT_SDK_DIR" >&2
    return 0
  fi
  echo "== Go: replace nxuskit-go -> ${NXUSKIT_GO_MOD_ROOT}" >&2
  local failed="" dir start elapsed name
  while IFS= read -r dir; do
    [[ -f "$dir/go.mod" ]] || continue
    echo "$dir" | grep -q "shared/" && continue
    name="${dir#$REPO_ROOT/}"
    start="$(_ms)"
    if (
      cd "$dir" && \
      go mod edit -replace "github.com/nxus-SYSTEMS/nxusKit/packages/nxuskit-go=${NXUSKIT_GO_MOD_ROOT}" && \
      go mod tidy && \
      mkdir -p bin && \
      CGO_ENABLED=1 go build -tags nxuskit -o bin/ ./...
    ); then
      elapsed=$(( $(_ms) - start ))
      emit_jsonl "$name" go build ok "$elapsed" ""
      if [[ "$RUN_TESTS" -eq 1 && "$BUILD_ONLY" -eq 0 ]]; then
        start="$(_ms)"
        if (cd "$dir" && CGO_ENABLED=1 go test -tags nxuskit ./... -short -count=1); then
          elapsed=$(( $(_ms) - start ))
          emit_jsonl "$name" go test ok "$elapsed" ""
        else
          elapsed=$(( $(_ms) - start ))
          emit_jsonl "$name" go test fail "$elapsed" "go test"
          failed="$failed $dir"
        fi
      fi
    else
      elapsed=$(( $(_ms) - start ))
      emit_jsonl "$name" go build fail "$elapsed" "go build"
      failed="$failed $dir"
    fi
  done < <(go_dirs_tiered)
  if [[ -n "$failed" ]]; then
    echo "error: Go failures:$failed" >&2
    return 1
  fi
}

python_phase() {
  if [[ "$BUILD_ONLY" -eq 1 ]]; then
    echo "skip: Python (--build-only skips Python import/--help)" >&2
    return 0
  fi
  if [[ -z "$PYTHON_SDK_ROOT" ]] || [[ ! -f "${PYTHON_SDK_ROOT}/pyproject.toml" ]]; then
    echo "skip: Python needs SDK python/pyproject.toml under \$NXUSKIT_SDK_DIR" >&2
    return 0
  fi
  if [[ -z "${NXUSKIT_LIB_PATH:-}" ]]; then
    echo "error: NXUSKIT_LIB_PATH not set — extract bundle with libnxuskit (see setup-sdk.sh)" >&2
    return 1
  fi
  local py_root
  py_root="$(cd "${PYTHON_SDK_ROOT}" && pwd)"
  export PYTHONPATH="${py_root}/src:${PYTHONPATH:-}"
  local failed="" rel dir start elapsed name ver

  start="$(_ms)"
  ver="$(python3 -c 'import nxuskit; print(nxuskit.__version__)' 2>/dev/null || echo "")"
  elapsed=$(( $(_ms) - start ))
  case "$ver" in
    0.9.*) ;;
    *)
      echo "error: nxuskit import/version check failed (got '${ver:-none}', expected 0.9.*)" >&2
      emit_jsonl "nxuskit" python import fail "$elapsed" "version $ver"
      return 1
      ;;
  esac
  echo "OK python nxuskit import version=$ver" >&2
  emit_jsonl "nxuskit" python import ok "$elapsed" "$ver"

  while IFS= read -r rel; do
    dir="${REPO_ROOT}/${rel}"
    [[ -d "$dir" ]] || continue
    name="$rel"
    if [[ "$DRY_RUN" -eq 1 ]]; then
      [[ -f "$dir/main.py" ]] || continue
      start="$(_ms)"
      if (cd "$dir" && python3 main.py --help >/dev/null 2>&1); then
        elapsed=$(( $(_ms) - start ))
        echo "OK python --help: $dir" >&2
        emit_jsonl "$name" python dry-run ok "$elapsed" ""
      else
        elapsed=$(( $(_ms) - start ))
        emit_jsonl "$name" python dry-run fail "$elapsed" "main.py --help"
        failed="$failed $dir"
      fi
    fi
  done < <(jq -r --arg t "$TIER" '
    .examples[]
    | select($t == "all" or .tier == $t)
    | .implementations.python // empty
    | select(length > 0)
  ' "${MANIFEST}")
  if [[ -n "$failed" ]]; then
    echo "error: Python failures:$failed" >&2
    return 1
  fi
}

bash_phase() {
  if ! command -v nxuskit-cli &>/dev/null; then
    echo "skip: Bash examples need nxuskit-cli on PATH" >&2
    return 0
  fi
  if ! command -v jq &>/dev/null; then
    echo "skip: Bash examples need jq" >&2
    return 0
  fi
  local failed="" dir name start elapsed
  while IFS= read -r rel; do
    dir="${REPO_ROOT}/${rel}"
    [[ -d "$dir" ]] || continue
    name="$rel"
    start="$(_ms)"
    if (cd "$dir" && make test >/dev/null 2>&1); then
      elapsed=$(( $(_ms) - start ))
      echo "OK bash test: $dir" >&2
      emit_jsonl "$name" bash test ok "$elapsed" ""
    else
      elapsed=$(( $(_ms) - start ))
      echo "FAIL bash test: $dir" >&2
      emit_jsonl "$name" bash test fail "$elapsed" "make test"
      failed="$failed $dir"
    fi
  done < <(jq -r --arg t "$TIER" '
    .examples[] |
    select(.implementations.bash != null) |
    select($t == "all" or .tier == $t) |
    .implementations.bash' "$MANIFEST")
  if [[ -n "$failed" ]]; then
    echo "error: Bash failures:$failed" >&2
    return 1
  fi
}

FAIL=0
case "$LANG" in
  rust)
    rust_build || FAIL=1
    ;;
  go)
    go_build || FAIL=1
    ;;
  python)
    python_phase || FAIL=1
    ;;
  all)
    rust_build || FAIL=1
    go_build || FAIL=1
    python_phase || FAIL=1
    bash_phase || FAIL=1
    ;;
  bash)
    bash_phase || FAIL=1
    ;;
  *) echo "error: --lang must be rust, go, python, bash, or all" >&2; exit 1 ;;
esac

if [[ "$SMOKE_RUN" -eq 1 && "$BUILD_ONLY" -eq 0 && "$FAIL" -eq 0 ]]; then
  smoke_all || FAIL=1
fi

if [[ "$BUILD_ONLY" -eq 1 ]]; then
  :
elif [[ "$DRY_RUN" -eq 0 ]] || [[ "$LANG" == "go" ]]; then
  echo "Note: use --dry-run with --lang python for main.py --help (Rust CLIs vary)." >&2
fi

if [[ "$JSON_OUT" -eq 1 ]]; then
  if [[ -f "${JSONL}" ]]; then
    jq -s '{ok: (all(.status == "ok")), results: .}' "${JSONL}"
  else
    jq -nc '{ok: true, results: []}'
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi

echo "OK: test-examples complete." >&2
exit 0
