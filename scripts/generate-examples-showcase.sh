#!/usr/bin/env bash
# generate-examples-showcase.sh — Generate examples/README.md showcase from manifest
#
# Usage: generate-examples-showcase.sh [--generate|--validate|--help]
#
# Reads conformance/examples_manifest.json and produces the auto-generated
# showcase sections for examples/README.md. Manual sections outside the
# marker comments are preserved.

set -euo pipefail

# --- Configuration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/conformance/examples_manifest.json"
README="$REPO_ROOT/examples/README.md"
BEGIN_MARKER="<!-- BEGIN: Auto-generated showcase (do not edit manually) -->"
END_MARKER="<!-- END: Auto-generated showcase -->"

# --- Argument parsing --------------------------------------------------------
MODE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --generate) MODE="generate"; shift ;;
        --validate) MODE="validate"; shift ;;
        --help|-h)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Error: unexpected argument: $1" >&2
            echo "Usage: $0 [--generate|--validate|--help]" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$MODE" ]]; then
    echo "Error: must specify --generate or --validate" >&2
    echo "Usage: $0 [--generate|--validate|--help]" >&2
    exit 1
fi

# --- Dependency check --------------------------------------------------------
if ! command -v jq &>/dev/null; then
    echo "Error: jq is required but not found. Install with: brew install jq" >&2
    exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
    echo "Error: manifest not found: $MANIFEST" >&2
    exit 1
fi

# --- Helper functions --------------------------------------------------------
title_case() {
    local name="$1"
    # Known acronyms that should stay uppercase
    echo "$name" | sed 's/-/ /g' | awk '{
        for (i=1; i<=NF; i++) {
            w = $i
            # Known acronyms
            if (w == "llm" || w == "clips" || w == "mcp" || w == "bn" || w == "zen") {
                $i = toupper(w)
            } else if (w == "lmstudio") {
                $i = "LM Studio"
            } else if (w == "cli") {
                $i = "CLI"
            } else if (w == "api") {
                $i = "API"
            } else {
                $i = toupper(substr(w,1,1)) substr(w,2)
            }
        }
        print
    }'
}

# --- Generate showcase content -----------------------------------------------
generate_showcase() {
    local manifest="$1"

    # Extract counts
    local total apps patterns integrations
    total=$(jq '.examples | length' "$manifest")
    apps=$(jq '[.examples[] | select(.category == "apps")] | length' "$manifest")
    patterns=$(jq '[.examples[] | select(.category == "patterns")] | length' "$manifest")
    integrations=$(jq '[.examples[] | select(.category == "integrations")] | length' "$manifest")

    # --- Header Block ---
    cat <<HEADER
# nxusKit Examples

A curated collection of **${total} production-ready examples** demonstrating LLM integration, rule engines, constraint solvers, Bayesian networks, and decision tables using the nxusKit SDK (nxuskit, nxuskit-go, nxuskit-py).

> **${apps} apps** | **${patterns} patterns** | **${integrations} integrations** — start with [Basic Chat](patterns/basic-chat/) or [Streaming](patterns/streaming/).

HEADER

    # --- Jump Bar ---
    cat <<'JUMPBAR'
**Browse by:** [Scenario](#by-scenario) | [Real-World Application](#by-real-world-application) | [Technology](#by-technology) | [Language](#by-language) | [Acronym and Tag Key](#acronym-and-tag-key)

---

JUMPBAR

    # --- Acronym and Tag Key ---
    cat <<'TAGKEY'
## Acronym and Tag Key

| Tag | Meaning |
|-----|---------|
| **LLM** | Large Language Model inference (chat, completion, streaming) |
| **CLIPS** | CLIPS (Rule-based Expert System Engine) |
| **Solver** | Z3 constraint solver |
| **BN** | Bayesian Network inference and learning |
| **ZEN** | ZEN decision table evaluation |
| **MCP** | Model Context Protocol |
| **Vision** | Vision and multimodal capabilities |
| **Streaming** | Server-Sent Events streaming responses |

---

TAGKEY

    # --- By Scenario Table ---
    echo "## By Scenario"
    echo ""
    echo "| Example | Tier | Category | Scenario | Real-World Application | Tags | Languages |"
    echo "|---------|------|----------|----------|----------------------|------|-----------|"

    jq -r '.examples[] | [.name, .category, (.tier // "community"), .scenario, .real_world_application, (.tech_tags | join(", ")), (.languages | map(gsub("^bash$";"CLI/Bash")) | join(", "))] | @tsv' "$manifest" | \
    while IFS=$'\t' read -r name category tier scenario app tags langs; do
        local display_name
        display_name=$(title_case "$name")
        local cat_label
        case "$category" in
            apps) cat_label="App" ;;
            patterns) cat_label="Pattern" ;;
            integrations) cat_label="Integration" ;;
            *) cat_label="$category" ;;
        esac
        local tier_label
        case "$tier" in
            pro) tier_label="Pro" ;;
            *) tier_label="Community" ;;
        esac
        echo "| [${display_name}](${category}/${name}/) | ${tier_label} | ${cat_label} | ${scenario} | ${app} | ${tags} | ${langs} |"
        # Emit scenario sub-rows
        jq -r --arg n "$name" '.examples[] | select(.name == $n) | .scenarios // [] | .[] | "| \u0026nbsp;\u0026nbsp;↳ `\(.name)` | | | \(.description) | | | |"' "$manifest"
    done

    echo ""
    echo "---"
    echo ""

    # --- By Real-World Application ---
    echo "## By Real-World Application"
    echo ""

    jq -r '[.examples[] | {app: .real_world_application, name: .name, category: .category}] | group_by(.app) | sort_by(.[0].app) | .[] | {app: .[0].app, examples: [.[] | {name, category}]}' "$manifest" | \
    jq -rs '.[] | "### \(.app)\n\(.examples | map("- [\(.name)](\(.category)/\(.name)/)") | join("\n"))\n"' 2>/dev/null || {
        # Fallback: simpler grouping approach
        local prev_app=""
        jq -r '.examples | sort_by(.real_world_application) | .[] | [.real_world_application, .name, .category] | @tsv' "$manifest" | \
        while IFS=$'\t' read -r app name category; do
            if [[ "$app" != "$prev_app" ]]; then
                [[ -n "$prev_app" ]] && echo ""
                echo "### ${app}"
                echo ""
                prev_app="$app"
            fi
            local display_name
            display_name=$(title_case "$name")
            echo "- [${display_name}](${category}/${name}/)"
        done
        echo ""
    }

    echo "---"
    echo ""

    # --- By Technology ---
    echo "## By Technology"
    echo ""

    local tags_ordered=("LLM" "CLIPS" "Solver" "BN" "ZEN" "MCP" "Vision" "Streaming")
    for tag in "${tags_ordered[@]}"; do
        local count
        count=$(jq --arg t "$tag" '[.examples[] | select(.tech_tags | index($t))] | length' "$manifest")
        if [[ "$count" -gt 0 ]]; then
            echo "### ${tag}"
            echo ""
            jq -r --arg t "$tag" '.examples[] | select(.tech_tags | index($t)) | [.name, .category] | @tsv' "$manifest" | \
            while IFS=$'\t' read -r name category; do
                local display_name
                display_name=$(title_case "$name")
                echo "- [${display_name}](${category}/${name}/)"
            done
            echo ""
        fi
    done

    echo "---"
    echo ""

    # --- By Language ---
    echo "## By Language"
    echo ""
    echo "| Example | Category | Rust | Go | Python |"
    echo "|---------|----------|------|-----|--------|"

    jq -r '.examples[] | [.name, .category, (if (.languages | index("rust")) then "yes" else "no" end), (if (.languages | index("go")) then "yes" else "no" end), (if (.languages | index("python")) then "yes" else "no" end)] | @tsv' "$manifest" | \
    while IFS=$'\t' read -r name category has_rust has_go has_python; do
        local display_name
        display_name=$(title_case "$name")
        local rust_col go_col python_col
        [[ "$has_rust" == "yes" ]] && rust_col="Yes" || rust_col="-"
        [[ "$has_go" == "yes" ]] && go_col="Yes" || go_col="-"
        [[ "$has_python" == "yes" ]] && python_col="Yes" || python_col="-"
        echo "| [${display_name}](${category}/${name}/) | ${category} | ${rust_col} | ${go_col} | ${python_col} |"
    done

    echo ""
}

# --- Untracked example detection (non-fatal) --------------------------------
check_untracked_examples() {
    local warn_count=0
    local dir dirname
    for dir in "$REPO_ROOT"/examples/patterns/*/ "$REPO_ROOT"/examples/integrations/*/ "$REPO_ROOT"/examples/apps/*/; do
        [[ -d "$dir" ]] || continue
        dirname=$(basename "$dir")
        [[ "$dirname" == "shared" || "$dirname" == "debug" ]] && continue
        if ! jq -e --arg n "$dirname" '.examples[] | select(.name == $n)' "$MANIFEST" &>/dev/null; then
            echo "Warning: untracked example directory: $dir" >&2
            warn_count=$((warn_count + 1))
        fi
    done
    if [[ "$warn_count" -gt 0 ]]; then
        echo "Warning: $warn_count untracked example directories found" >&2
    fi
}

# --- Generate mode -----------------------------------------------------------
do_generate() {
    if [[ ! -f "$README" ]]; then
        echo "Error: README not found: $README" >&2
        exit 1
    fi

    if ! grep -qF "$BEGIN_MARKER" "$README"; then
        # No markers yet — wrap generated content in markers, preserve manual sections
        local manual_start
        {
            echo "$BEGIN_MARKER"
            echo ""
            cat "$TMPDIR/showcase.md"
            echo ""
            echo "$END_MARKER"
            echo ""
            # Extract manual sections: everything from "## Quick Start" onward
            manual_start=$(grep -n "^## Quick Start\|^## Interactive Modes" "$README" | head -1 | cut -d: -f1)
            if [[ -n "$manual_start" ]]; then
                tail -n +"$manual_start" "$README"
            fi
        } > "$TMPDIR/new_readme.md"
        cp "$TMPDIR/new_readme.md" "$README"
        echo "Generated: $README (markers inserted, manual sections preserved)" >&2
    else
        # Markers exist — replace content between them
        local begin_line end_line
        begin_line=$(grep -nF "$BEGIN_MARKER" "$README" | head -1 | cut -d: -f1)
        end_line=$(grep -nF "$END_MARKER" "$README" | head -1 | cut -d: -f1)

        if [[ -z "$begin_line" || -z "$end_line" ]]; then
            echo "Error: could not find both markers in $README" >&2
            exit 1
        fi

        {
            head -n "$begin_line" "$README"
            echo ""
            cat "$TMPDIR/showcase.md"
            echo ""
            tail -n +"$end_line" "$README"
        } > "$TMPDIR/new_readme.md"
        cp "$TMPDIR/new_readme.md" "$README"
        echo "Regenerated: $README (content between markers replaced)" >&2
    fi

    check_untracked_examples

    # Also update root README.md (if it has EXAMPLES-TABLE markers)
    update_root_readme
}

# --- Root README table generation --------------------------------------------
update_root_readme() {
    local root_readme="$REPO_ROOT/README.md"
    local root_begin="<!-- EXAMPLES-TABLE:START -->"
    local root_end="<!-- EXAMPLES-TABLE:END -->"

    if [[ ! -f "$root_readme" ]]; then
        return
    fi
    if ! grep -qF "$root_begin" "$root_readme"; then
        return
    fi

    local manifest="$MANIFEST"

    # Generate category tables with scenario sub-rows
    {
        echo "### Patterns — Reusable SDK integration patterns"
        echo ""
        echo "| Example | Description | Languages |"
        echo "|---------|-------------|-----------|"
        generate_root_table_rows "$manifest" "patterns"
        echo ""

        echo "### Integrations — Combining SDK features"
        echo ""
        echo "| Example | Description | Languages |"
        echo "|---------|-------------|-----------|"
        generate_root_table_rows "$manifest" "integrations"
        echo ""

        echo "### Apps — Complete applications"
        echo ""
        echo "| Example | Description | Languages |"
        echo "|---------|-------------|-----------|"
        generate_root_table_rows "$manifest" "apps"
    } > "$TMPDIR/root_tables.md"

    # Replace content between markers
    local begin_line end_line
    begin_line=$(grep -nF "$root_begin" "$root_readme" | head -1 | cut -d: -f1)
    end_line=$(grep -nF "$root_end" "$root_readme" | head -1 | cut -d: -f1)

    if [[ -z "$begin_line" || -z "$end_line" ]]; then
        echo "Warning: could not find both EXAMPLES-TABLE markers in root README.md" >&2
        return
    fi

    {
        head -n "$begin_line" "$root_readme"
        echo ""
        cat "$TMPDIR/root_tables.md"
        echo ""
        tail -n +"$end_line" "$root_readme"
    } > "$TMPDIR/new_root_readme.md"
    cp "$TMPDIR/new_root_readme.md" "$root_readme"
    echo "Regenerated: $root_readme (EXAMPLES-TABLE content replaced)" >&2
}

generate_root_table_rows() {
    local manifest="$1"
    local category="$2"

    jq -r --arg cat "$category" '.examples[] | select(.category == $cat) | [.name, .description, (.languages | map(. | gsub("^bash$";"CLI/Bash") | gsub("^r";"R") | gsub("^g";"G") | gsub("^p";"P")) | join(", "))] | @tsv' "$manifest" | \
    while IFS=$'\t' read -r name desc langs; do
        echo "| [${name}](examples/${category}/${name}/) | ${desc} | ${langs} |"
        # Scenario sub-rows
        jq -r --arg n "$name" '.examples[] | select(.name == $n) | .scenarios // [] | .[] | "| \u0026nbsp;\u0026nbsp;↳ `\(.name)` | \(.description) | |"' "$manifest"
    done
}

# --- Validate mode -----------------------------------------------------------
do_validate() {
    if [[ ! -f "$README" ]]; then
        echo "FAIL: README not found: $README" >&2
        exit 1
    fi

    if ! grep -qF "$BEGIN_MARKER" "$README" || ! grep -qF "$END_MARKER" "$README"; then
        echo "FAIL: markers not found in $README" >&2
        exit 1
    fi

    local begin_line end_line
    begin_line=$(grep -nF "$BEGIN_MARKER" "$README" | head -1 | cut -d: -f1)
    end_line=$(grep -nF "$END_MARKER" "$README" | head -1 | cut -d: -f1)

    # Extract current content between markers, normalize whitespace for comparison
    sed -n "$((begin_line + 1)),$((end_line - 1))p" "$README" | sed '/./,$!d' | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' > "$TMPDIR/current.md"
    sed '/./,$!d' "$TMPDIR/showcase.md" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' > "$TMPDIR/expected.md"

    if diff -q "$TMPDIR/current.md" "$TMPDIR/expected.md" &>/dev/null; then
        echo "PASS: showcase is up to date" >&2
        check_untracked_examples
        exit 0
    else
        echo "FAIL: showcase is out of date. Differences:" >&2
        diff -u "$TMPDIR/current.md" "$TMPDIR/expected.md" >&2 || true
        exit 1
    fi
}

# --- Main logic --------------------------------------------------------------
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# Generate showcase content
generate_showcase "$MANIFEST" > "$TMPDIR/showcase.md"

if [[ "$MODE" == "generate" ]]; then
    do_generate
elif [[ "$MODE" == "validate" ]]; then
    do_validate
fi
