# Example title (replace)

**Summary:** One sentence describing what the reader runs and learns.

## Edition

**Community** or **Pro** — must match the `tier` field for this example in `conformance/examples_manifest.json`.

## What this demonstrates

- **Summary:** `description` from the manifest  
- **Scenario:** `scenario` from the manifest  
- **`tech_tags`:** enumerated tags for the example (`name` keys `conformance/examples_manifest.json`)  
- Optional extra bullets for UX details not captured in the manifest

## Language implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available / planned |
| Go | `go/` | … |
| Python | `python/` | … |

## Prerequisites

- **SDK:** installed tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH`) — root [README.md](../README.md), `setup-sdk.sh`, `test-examples.sh`
- **Languages:** which of rust / go / python exist for this example (paths in **Language implementations**)
- **Models / CLIPS / MCP:** add only when `tech_tags` imply them (LLM, Vision, Streaming → provider keys / Ollama; CLIPS → CLIPS-enabled SDK; MCP → host/fixtures)
- **CLIPS attribution:** for CLIPS-heavy examples, link to the root README's "A Word About CLIPS" section instead of duplicating the full attribution in every generated README.

## Build

```bash
# Rust
cd rust && cargo build

# Go
cd go && make build

# Python
cd python && python3 main.py --help
```

## Run

Add concrete commands (env vars, flags) for a minimal successful run.

## See also

- `conformance/examples_manifest.json` — canonical name, tier, and paths
- Maintainers: `scripts/normalize_example_readme_build_run.py` injects manifest **What** / **Prerequisites** / **Build** / **Run** conventions (CI dry-run)
- Any SDK doc links your example depends on
