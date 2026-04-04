# Arbiter - Auto-Retry LLM with CLIPS Validation

A command-line tool demonstrating the Solver pattern: using CLIPS rules to evaluate LLM output quality and automatically retry with adjusted parameters when validation fails.

> Stop accepting unreliable LLM output — validate every response against CLIPS rules and retry automatically until your standards are met.

**Scenarios**: `classification` · `extraction` · `reasoning`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS

- **Summary:** CLIPS-validated LLM retry app with rule-based answer verification
- **Scenario:** Submit questions to an LLM and validate answers against CLIPS rules, retrying on validation failure
- **`tech_tags` in manifest:** `CLIPS, LLM` — example id **`arbiter`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Real-World Application

Operations research tool, constraint modeling workbench.

## Requirements

**Edition**: nxusKit Pro  
This example requires the Pro edition of nxusKit. [Purchase Pro](https://nxus.systems/pro) or start a free 30-day trial (automatic on first Pro feature call).

## Technologies

Solver

## CLIPS integration path (validation)

Go CLIPS validation uses **provider chat** with local `go/clips_wire.go` types mirroring `ClipsInput` / `ClipsOutput`. For **Session API** access, use `nxuskit.ClipsSession`. Reference: `conformance/clips-json-contract.json`; nxusKit SDK `sdk-packaging/docs/rule-authoring.md` — **ClipsInput JSON Reference** (`#clipsinput-json-reference`; bundle: `docs/rule-authoring.md`).

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/arbiter`:
cd rust && cargo build
cd go && make build
```
## Features

- **LLM Output Validation** - Use CLIPS rules to evaluate response quality
- **Automatic Retry** - Retry with adjusted parameters on validation failure
- **Configurable Strategies** - Define retry strategies for different failure modes
- **Multiple Conclusion Types** - Classification, extraction, and reasoning tasks
- **Scoring System** - Score attempts based on validation results

## Installation

### Rust

```bash
cd examples/apps/arbiter/rust
cargo build --release
```

### Go

```bash
cd examples/apps/arbiter/go
make build
```

## Run

### Rust

```bash
cd examples/apps/arbiter/rust

# Show help
cargo run -- --help

# Run classification task
cargo run -- -t classification -i "This product is amazing!" --categories "positive,negative,neutral"

# Run with custom config
cargo run -- -c config.yaml -i "Analyze this text"

# Run extraction task
cargo run -- -t extraction -i "John works at Acme Corp in New York"

# Verbose mode
cargo run -- -v -t reasoning -i "If A implies B and B implies C, what can we conclude about A and C?"
```

### Go

```bash
cd examples/apps/arbiter/go

# Show help
./bin/arbiter --help

# Run classification
./bin/arbiter -t classification -i "Great service!" --categories "positive,negative,neutral"
```

## Command Line Options

```
USAGE:
    arbiter [OPTIONS] -i <INPUT>

OPTIONS:
    -c, --config <FILE>       Configuration file path
    -i, --input <TEXT>        Input text to process
    -t, --type <TYPE>         Conclusion type: classification, extraction, reasoning
    --categories <LIST>       Comma-separated categories for classification
    --max-retries <N>         Maximum retry attempts (default: 3)
    -v, --verbose             Show detailed progress
    -h, --help                Show help message
```

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
./bin/arbiter --verbose       # Go

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
./bin/arbiter --step          # Go

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Conclusion Types

### Classification
Categorize input into predefined categories.

```bash
arbiter -t classification -i "I love this!" --categories "positive,negative,neutral"
```

### Extraction
Extract structured information from text.

```bash
arbiter -t extraction -i "Contact John at john@example.com or 555-1234"
```

### Reasoning
Perform logical reasoning and inference.

```bash
arbiter -t reasoning -i "All cats are mammals. Whiskers is a cat. What is Whiskers?"
```

## Configuration

Create a YAML configuration file for custom settings:

```yaml
# arbiter-config.yaml
max_retries: 5
strategies:
  - failure_type: invalid_category
    adjustments:
      temperature: -0.2
      prompt_suffix: "Choose only from the given categories."
  - failure_type: incomplete_extraction
    adjustments:
      temperature: 0
      prompt_suffix: "Extract all mentioned entities."
  - failure_type: invalid_reasoning
    adjustments:
      temperature: -0.1
      prompt_suffix: "Show your reasoning step by step."
```

## Example Output

### Classification Result

```
=== Solver: Classification Task ===

Input: "This product exceeded my expectations!"
Categories: positive, negative, neutral

Attempt 1:
  LLM Response: "positive"
  Validation: PASSED
  Score: 100

Result: positive (1 attempt, 45ms)
```

### With Retry

```
=== Solver: Classification Task ===

Input: "It's okay I guess"
Categories: positive, negative, neutral

Attempt 1:
  LLM Response: "somewhat positive"
  Validation: FAILED (invalid category)
  Strategy: Reduce temperature, clarify categories

Attempt 2:
  LLM Response: "neutral"
  Validation: PASSED
  Score: 95

Result: neutral (2 attempts, 1.2s)
```

## Retry Strategies

The arbiter includes default strategies for common failure modes:

| Failure Type | Adjustment |
|--------------|------------|
| Invalid category | Lower temperature, clarify options |
| Incomplete extraction | Reset temperature, request all entities |
| Invalid reasoning | Lower temperature, request step-by-step |
| Confidence too low | Increase temperature slightly |
| Format error | Add format examples to prompt |

## Architecture

```
arbiter/
├── rust/
│   ├── src/main.rs         # CLI entry point
│   └── Cargo.toml
├── go/
│   ├── cmd/main.go         # CLI entry point
│   ├── solver.go           # Core solver logic
│   ├── strategies.go       # Retry strategies
│   ├── validator.go        # CLIPS validation
│   └── go.mod
└── shared/
    ├── rules/              # CLIPS validation rules
    └── configs/            # Example configurations
```

## How It Works

1. **Initial Request**: Send input to LLM with configured prompt
2. **Validation**: Pass LLM response through CLIPS validation rules
3. **Evaluation**: Score the response based on validation results
4. **Retry Decision**: If validation fails, find matching retry strategy
5. **Adjustment**: Apply strategy adjustments (temperature, prompt, etc.)
6. **Repeat**: Retry up to max_retries times
7. **Result**: Return best successful attempt or highest-scoring failure

## Notes

- CLIPS validation rules are in `shared/rules/classification-eval.clp`
- Build Go with `-tags=clips` for real ClipsProvider integration
- LLM approach requires API key (ANTHROPIC_API_KEY or OPENAI_API_KEY)

## Testing

```bash
# Rust
cd examples/apps/arbiter/rust
cargo test

# Go
cd examples/apps/arbiter/go
go test -v ./...
```

## License

Part of the nxusKit project.
