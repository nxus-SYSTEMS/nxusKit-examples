# Puzzler - Puzzle Solver Comparison

A command-line tool for comparing three approaches to solving logic puzzles: CLIPS-only, LLM-only, and Hybrid.

> Compare CLIPS rule-based constraint solving against LLM reasoning side by side, then combine both in a hybrid approach for real puzzle problems.

**Scenarios**: `sudoku` · `set-game` · `compare`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** 🏁 · LLM · CLIPS · Solver

- **Summary:** Multi-approach puzzle solver comparing CLIPS, LLM, and hybrid strategies
- **Scenario:** Compare CLIPS rule-based, LLM reasoning, and hybrid approaches for solving logic puzzles
- **`tech_tags` in manifest:** `CLIPS, LLM, Solver` — example id **`puzzler`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Real-World Application

Educational puzzle solver, constraint programming tutorial.

## Requirements

**Edition**: nxusKit Pro  
This example requires the Pro edition of nxusKit. [Purchase Pro](https://nxus.systems/pro) or start a free 30-day trial (automatic on first Pro feature call).

## Technologies

Solver

## CLIPS integration path (CLIPS-only / hybrid modes)

The Go CLIPS solver path uses **provider chat** (`go/clips_wire.go` mirrors `ClipsInput` / `ClipsOutput` JSON). It is not the **Session API** (`nxuskit.ClipsSession`). See `conformance/clips-json-contract.json` and nxusKit SDK `sdk-packaging/docs/rule-authoring.md` — **ClipsInput JSON Reference** (`#clipsinput-json-reference`; bundle: `docs/rule-authoring.md`).

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/puzzler`:
cd rust && cargo build
cd go && make build
```
## Features

- **Sudoku Puzzles** - Solve Sudoku puzzles of varying difficulty
- **Set Game** - Find valid sets in Set card game hands
- **Three Approaches**:
  - **CLIPS-only**: Pure rule-based constraint propagation
  - **LLM-only**: Pure LLM reasoning
  - **Hybrid**: CLIPS primary with LLM fallback for stuck states
- **Comparison Mode** - Run all approaches and compare results

## Installation

### Rust

```bash
cd examples/apps/puzzler/rust
cargo build --release
```

### Go

```bash
cd examples/apps/puzzler/go
make build
```

## Run

### Rust

```bash
cd examples/apps/puzzler/rust

# Show help
cargo run -- --help

# Solve a Sudoku puzzle
cargo run -- sudoku -p easy

# Compare all approaches on Sudoku
cargo run -- sudoku --compare

# Play Set game
cargo run -- set -p random

# Compare approaches on Set game
cargo run -- set --compare
```

### Go

```bash
cd examples/apps/puzzler/go

# Show help
./bin/puzzler --help

# Solve a Sudoku puzzle
./bin/puzzler sudoku -p easy

# Compare all approaches
./bin/puzzler sudoku --compare
```

## Command Line Options

```
USAGE:
    puzzler [OPTIONS] <GAME>

GAMES:
    sudoku    Solve Sudoku puzzles
    set       Find sets in Set game cards

OPTIONS:
    -p, --puzzle <ID>       Puzzle identifier (easy, medium, hard, expert, or custom)
    -a, --approach <TYPE>   Solver approach: clips, llm, hybrid (default: hybrid)
    -c, --compare           Compare all three approaches
    -v, --verbose           Show detailed solving steps
    -h, --help              Show help message
```

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
./bin/puzzler --verbose       # Go

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
./bin/puzzler --step          # Go

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Puzzle Types

### Sudoku

Difficulty levels:
- **easy** - Many given numbers, straightforward solving
- **medium** - Moderate difficulty
- **hard** - Requires advanced techniques
- **expert** - Very few givens, requires backtracking

### Set Game

Find valid sets where each attribute (color, shape, shading, number) is either all the same or all different across three cards.

## Example Output

### Sudoku Comparison

```
=== Sudoku Puzzle: easy ===

Approach      | Time    | Solved | Moves
--------------|---------|--------|-------
CLIPS-only    | 12ms    | Yes    | 47
LLM-only      | 2.3s    | Yes    | 52
Hybrid        | 15ms    | Yes    | 47

Winner: CLIPS-only (fastest)
```

### Set Game

```
=== Set Game: 12 cards ===

Found 3 valid sets:

Set 1: Red-Oval-Solid-1, Red-Oval-Striped-2, Red-Oval-Empty-3
Set 2: Green-Diamond-Solid-1, Purple-Diamond-Striped-1, Red-Diamond-Empty-1
Set 3: ...
```

## Architecture

```
puzzler/
├── rust/
│   ├── src/main.rs         # CLI entry point
│   └── Cargo.toml
├── go/
│   ├── cmd/main.go         # CLI entry point
│   ├── sudoku.go           # Sudoku solver logic
│   ├── setgame.go          # Set game solver logic
│   └── go.mod
└── shared/
    └── puzzles/            # Puzzle definitions
```

## Notes

- CLIPS validation rules are in `shared/puzzles/`
- LLM solving uses Ollama by default (no API key required)
- Optional: Set ANTHROPIC_API_KEY or OPENAI_API_KEY for cloud providers

## Testing

```bash
# Rust
cd examples/apps/puzzler/rust
cargo test

# Go
cd examples/apps/puzzler/go
go test -v ./...
```

## License

Part of the nxusKit project.
