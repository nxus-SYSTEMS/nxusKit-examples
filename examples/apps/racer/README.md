# Racer - CLIPS vs LLM Head-to-Head Competition

A benchmarking tool for running concurrent races between CLIPS rule-based solving and LLM reasoning on logic problems.

> Race CLIPS rule engines against LLMs on logic puzzles and let the data choose your AI strategy.

**Scenarios**: `race` · `benchmark` · `list` · `describe`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## Real-World Application

Motorsport strategy advisor, real-time decision engine.

## Requirements

**Edition**: nxusKit Pro  
This example requires the Pro edition of nxusKit. [Purchase Pro](https://nxus.systems/pro) or start a free 30-day trial (automatic on first Pro feature call).

## Technologies

CLIPS

## What this demonstrates

**Difficulty: Advanced** 🏁 · LLM · CLIPS

- **Summary:** CLIPS rule-based racing strategy engine
- **Scenario:** Simulate racing pit-stop strategy using CLIPS rules
- **`tech_tags` in manifest:** `CLIPS` — example id **`racer`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## CLIPS integration path

The Go CLIPS runner uses **provider chat** (`go/clips_wire.go`). For **Session API** usage, use CLIPS session bindings in the SDK. Reference: `conformance/clips-json-contract.json`; nxusKit SDK `sdk-packaging/docs/rule-authoring.md` — **ClipsInput JSON Reference** (`#clipsinput-json-reference`; bundle: `docs/rule-authoring.md`).

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/racer`:
cd rust && cargo build
cd go && make build
```
## Features

- **Head-to-Head Racing** - Run CLIPS and LLM approaches simultaneously
- **Benchmarking** - Statistical analysis over multiple runs
- **Problem Library** - Built-in collection of logic problems
- **Scoring Modes** - Speed, accuracy, or composite scoring
- **JSON Output** - Machine-readable results for analysis

## Installation

### Rust

```bash
cd examples/apps/racer/rust
cargo build --release
```

### Go

```bash
cd examples/apps/racer/go
make build
```

## Run

### Rust

```bash
cd examples/apps/racer/rust

# Show help
cargo run -- --help

# Run a single race
cargo run -- race einstein-riddle

# Run with accuracy scoring
cargo run -- race -s accuracy family-relations

# Benchmark with 20 runs
cargo run -- benchmark -n 20 einstein-riddle -o results.json

# List available problems
cargo run -- list

# Describe a specific problem
cargo run -- describe einstein-riddle
```

### Go

```bash
cd examples/apps/racer/go

# Show help
./bin/racer --help

# Run a single race
./bin/racer race einstein-riddle

# Benchmark mode
./bin/racer benchmark -n 10 logic-grid
```

## Commands

### race

Run a single head-to-head race between CLIPS and LLM.

```bash
racer race <PROBLEM> [OPTIONS]

OPTIONS:
    -s, --scoring <MODE>   Scoring: speed, accuracy, composite (default: speed)
    -t, --timeout <SECS>   Timeout per approach (default: 60)
    -m, --model <MODEL>    LLM model to use
    --clips-only           Run only CLIPS approach
    --llm-only             Run only LLM approach
    -j, --json             Output in JSON format
    -v, --verbose          Show detailed progress
```

### benchmark

Run multiple races for statistical analysis.

```bash
racer benchmark <PROBLEM> [OPTIONS]

OPTIONS:
    -n, --runs <N>         Number of benchmark runs (default: 10)
    -o, --output <FILE>    Write results to file
    -j, --json             Output in JSON format
```

### list

List available problems with optional filtering.

```bash
racer list [OPTIONS]

OPTIONS:
    -t, --type <TYPE>      Filter by problem type
    -d, --difficulty       Filter by difficulty
```

### describe

Show detailed information about a problem.

```bash
racer describe <PROBLEM>
```

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
./bin/racer --verbose       # Go

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
./bin/racer --step          # Go

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Problem Types

- **einstein-riddle** - The classic Einstein's Riddle (Zebra Puzzle)
- **family-relations** - Family relationship deduction
- **logic-grid** - Logic grid puzzles
- **scheduling** - Resource scheduling problems
- **classification** - Multi-attribute classification

## Scoring Modes

- **speed** - Fastest correct answer wins
- **accuracy** - Most accurate/complete answer wins
- **composite** - Weighted combination of speed and accuracy

## Example Output

### Race Results

```
=== Race: einstein-riddle ===

Contender    | Time    | Correct | Score
-------------|---------|---------|-------
CLIPS        | 45ms    | Yes     | 100
LLM (Claude) | 3.2s    | Yes     | 98

Winner: CLIPS (faster with equal accuracy)
```

### Benchmark Results

```
=== Benchmark: einstein-riddle (20 runs) ===

Contender    | Avg Time | Win Rate | Avg Score
-------------|----------|----------|----------
CLIPS        | 47ms     | 85%      | 99.5
LLM (Claude) | 3.4s     | 15%      | 97.2

Statistical Winner: CLIPS (p < 0.001)
```

## Architecture

```
racer/
├── rust/
│   ├── src/main.rs         # CLI entry point
│   └── Cargo.toml
├── go/
│   ├── cmd/main.go         # CLI entry point
│   ├── runner.go           # Race runner logic
│   ├── problems.go         # Problem definitions
│   └── go.mod
└── shared/
    └── problems/           # Problem definitions
```

## Notes

- CLIPS functionality uses ClipsProvider for rule execution
- LLM approach requires API key (ANTHROPIC_API_KEY or OPENAI_API_KEY)
- Benchmarks may vary based on LLM response times

## Testing

```bash
# Rust
cd examples/apps/racer/rust
cargo test

# Go
cd examples/apps/racer/go
go test -v ./...
```

## License

Part of the nxusKit project.
