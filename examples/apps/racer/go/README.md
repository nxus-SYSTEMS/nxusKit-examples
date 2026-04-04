# Racer - CLIPS vs LLM Racing (Go)

A benchmarking framework that races CLIPS and LLM approaches head-to-head on logic puzzles and constraint satisfaction problems.

> Race CLIPS rule engines against LLMs on logic puzzles and let the data choose your AI strategy.

**Scenarios**: `race` · `benchmark` · `list` · `describe`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS

- **Summary:** CLIPS rule-based racing strategy engine
- **Scenario:** Simulate racing pit-stop strategy using CLIPS rules
- **`tech_tags` in manifest:** `CLIPS` — example id **`racer`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## Overview

The Racer runs both CLIPS and LLM solvers concurrently on the same problem, measuring:

- **Correctness** - Does the answer match the expected solution?
- **Speed** - How long did each approach take?
- **Resource usage** - Token consumption for LLM, rules fired for CLIPS
- **Timeout handling** - Graceful handling of approaches that take too long

## Features

### Concurrent Execution
Both runners execute simultaneously using goroutines, with configurable timeout per approach.

### Scoring Modes

| Mode | Description |
|------|-------------|
| `speed` | Winner is fastest correct answer |
| `accuracy` | Winner is most accurate (ties broken by speed) |
| `efficiency` | Winner balances speed and resource cost |

### Problem Types

- Einstein-style logic riddles
- Constraint satisfaction problems
- Planning/scheduling problems
- Any problem expressible in CLIPS rules

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/racer/go`:
cd ../rust && cargo build
make build
```

## Run

### Race on a Logic Problem

```bash
cd packages/nxuskit-go/examples/racer

go run ./cmd/racer race \
  --problem einstein-riddle \
  --timeout 60s \
  --scoring speed
```

### Run Multiple Races

```bash
go run ./cmd/racer tournament \
  --problems-dir testdata/problems \
  --timeout 30s \
  --format json
```

### Custom Problem

```bash
go run ./cmd/racer race \
  --problem-file custom_problem.json \
  --rules-dir ./rules \
  --timeout 120s
```

## Problem File Format

```json
{
  "id": "einstein-riddle",
  "name": "Einstein's Riddle",
  "description": "Who owns the fish?",
  "constraints": [...],
  "expected_solution": {
    "german": "fish"
  }
}
```

## Output Example

```
🏁 Race: Einstein Riddle
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLIPS Runner:
  Status: ✓ Complete
  Time: 234ms
  Answer: German owns fish
  Correct: ✓

LLM Runner:
  Status: ✓ Complete
  Time: 4521ms
  Tokens: 2340
  Answer: German owns fish
  Correct: ✓

Winner: CLIPS (19x faster)
```

## LLM Provider Configuration

The LLM runner uses the provider fallback chain:

```bash
# Default order
export LLMKIT_PROVIDER_SEQUENCE="ollama,claude,openai"

# For production (cloud-first)
export LLMKIT_PROVIDER_SEQUENCE="claude,openai,ollama"
```

## Running Tests

```bash
go test -v ./...
```

## CLIPS Feature

For CLIPS execution using ClipsProvider:
```bash
go build -tags clips ./...
```

This enables CLIPS-based constraint solving.
