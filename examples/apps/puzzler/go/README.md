# Puzzler - Puzzle Solving Comparison (Go)

A puzzle-solving framework that compares CLIPS-only, LLM-only, and Hybrid solving approaches for Sudoku puzzles and Set card game recognition.

> Compare CLIPS rule-based constraint solving against LLM reasoning side by side, then combine both in a hybrid approach for real puzzle problems.

**Scenarios**: `sudoku` · `set-game` · `compare`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS · Solver

- **Summary:** Multi-approach puzzle solver comparing CLIPS, LLM, and hybrid strategies
- **Scenario:** Compare CLIPS rule-based, LLM reasoning, and hybrid approaches for solving logic puzzles
- **`tech_tags` in manifest:** `CLIPS, LLM, Solver` — example id **`puzzler`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Overview

The Puzzler demonstrates three different approaches to solving logic puzzles:

| Approach | Description | Strengths |
|----------|-------------|-----------|
| **CLIPS-only** | Pure rule-based solving using CLIPS expert system | Fast, deterministic, no API costs |
| **LLM-only** | Uses LLM for reasoning through the puzzle | Flexible, handles novel patterns |
| **Hybrid** | CLIPS for constraint propagation + LLM for stuck states | Best of both worlds |

## Supported Puzzles

### Sudoku
- Standard 9x9 grid puzzles
- Difficulty levels: easy, medium, hard, expert
- Validates solutions against constraints

### Set Card Game
- Find valid sets in a 12-card hand
- Validates set correctness (all same or all different per attribute)

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/puzzler/go`:
cd ../rust && cargo build
make build
```

## Run

### Solve Sudoku with All Approaches

```bash
cd packages/nxuskit-go/examples/puzzler

go run ./cmd/puzzler solve \
  --puzzle testdata/medium_sudoku.json \
  --approaches clips,llm,hybrid \
  --format json
```

### Find Sets in a Hand

```bash
go run ./cmd/puzzler sets \
  --hand testdata/sample_hand.json \
  --format json
```

### Compare Approaches

```bash
go run ./cmd/puzzler compare \
  --puzzle testdata/hard_sudoku.json \
  --format markdown
```

## LLM Provider Fallback

The Puzzler uses the provider fallback chain:

1. **Ollama** (local) - Default if running
2. **Anthropic** - If `ANTHROPIC_API_KEY` is set
3. **OpenAI** - If `OPENAI_API_KEY` is set

Configure via environment:
```bash
export LLMKIT_PROVIDER_SEQUENCE="ollama,claude,openai"
```

## Output Formats

### JSON Format
```json
{
  "puzzle": "medium",
  "results": [
    {
      "approach": "clips_only",
      "correct": true,
      "time_ms": 45,
      "tokens_used": 0
    },
    {
      "approach": "llm_only",
      "correct": true,
      "time_ms": 2340,
      "tokens_used": 1250
    }
  ],
  "winner": "clips_only"
}
```

### Markdown Format
```
# Sudoku Solution Comparison

| Approach | Correct | Time | Tokens |
|----------|---------|------|--------|
| CLIPS    | ✓       | 45ms | 0      |
| LLM      | ✓       | 2.3s | 1250   |
| Hybrid   | ✓       | 120ms| 150    |

**Winner**: CLIPS (fastest correct solution)
```

## Running Tests

```bash
go test -v ./...
```

## CLIPS Feature

To use CLIPS validation with ClipsProvider:
```bash
go build -tags clips ./...
```

This enables CLIPS-based puzzle validation.
