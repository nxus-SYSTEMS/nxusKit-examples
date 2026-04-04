# Ruler - Natural Language to CLIPS Rule Generation

A command-line tool for generating CLIPS rules from natural language descriptions using LLM, with validation and automatic retry logic.

> Turn plain English into validated CLIPS rules — describe your business logic, get production-ready expert system code with automatic error correction.

**Scenarios**: `generate` · `validate` · `save` · `load` · `examples`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS

- **Summary:** CLIPS rule authoring and execution app
- **Scenario:** Author, load, and execute CLIPS rules interactively
- **`tech_tags` in manifest:** `CLIPS` — example id **`ruler`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## Real-World Application

Business rules workbench, rule management console.

## Requirements

**Edition**: nxusKit Pro  
This example requires the Pro edition of nxusKit. [Purchase Pro](https://nxus.systems/pro) or start a free 30-day trial (automatic on first Pro feature call).

## Technologies

CLIPS

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/ruler`:
cd rust && cargo build
cd go && make build
```
## Features

- **Natural Language Input** - Describe rules in plain English
- **CLIPS Code Generation** - Produces valid CLIPS deftemplates and defrules
- **Automatic Validation** - Validates generated code against CLIPS syntax
- **Retry with Feedback** - Automatically retries with error feedback on failures
- **Progressive Examples** - Built-in examples from basic to advanced complexity
- **Multiple Output Formats** - Save as .clp, .json, or binary

## Installation

### Rust

```bash
cd examples/apps/ruler/rust
cargo build --release
```

### Go

```bash
cd examples/apps/ruler/go
make build
```

## Run

### Rust

```bash
cd examples/apps/ruler/rust

# Show help
cargo run -- --help

# Generate rules from natural language
cargo run -- generate "Create a rule that classifies adults if age >= 18"

# Generate with advanced complexity
cargo run -- generate -c advanced "Medical triage expert system" -o triage.clp

# Run progressive examples
cargo run -- examples -c basic

# Validate existing CLIPS code
cargo run -- validate my-rules.clp

# Load and display rules
cargo run -- load my-rules.clp
```

### Go

```bash
cd examples/apps/ruler/go

# Show help
./bin/ruler --help

# Generate rules
./bin/ruler generate "Classify customers as gold if purchases > 5000"

# Generate with output file
./bin/ruler generate -o customer.clp "Customer loyalty program rules"
```

## Commands

### generate

Generate CLIPS rules from a natural language description.

```bash
ruler generate <DESCRIPTION> [OPTIONS]

OPTIONS:
    -c, --complexity <LEVEL>  Target complexity: basic, intermediate, advanced
    -m, --model <MODEL>       LLM model to use (default: claude-haiku-4-5-20251001)
    -r, --retries <N>         Max retry attempts (default: 5)
    -o, --output <FILE>       Write output to file
    -j, --json                Output in JSON format
    -v, --verbose             Show detailed progress
```

### validate

Validate CLIPS code syntax and structure.

```bash
ruler validate <FILE> [OPTIONS]

OPTIONS:
    -v, --verbose    Show detailed validation results
```

### examples

Run built-in progressive complexity examples.

```bash
ruler examples [OPTIONS]

OPTIONS:
    -c, --complexity <LEVEL>  Filter by complexity level
    -l, --list                List examples without running
```

### save / load

Save or load rule sets.

```bash
ruler save <FILE>    # Save current rules
ruler load <FILE>    # Load rules from file
```

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
./bin/ruler --verbose       # Go

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
./bin/ruler --step          # Go

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Complexity Levels

### Basic
- Simple single-rule definitions
- Basic deftemplates with few slots
- Straightforward conditions

Example: "Classify people as adults if age >= 18"

### Intermediate
- Multiple related rules
- Fact chaining and dependencies
- Moderate slot complexity

Example: "Customer loyalty program with bronze, silver, gold tiers"

### Advanced
- Complex multi-rule systems
- Salience and conflict resolution
- Advanced pattern matching

Example: "Medical triage system with symptom analysis"

## Example Output

### Generated CLIPS Code

```clp
; Generated by Ruler from: "Classify adults if age >= 18"

(deftemplate person
   (slot name (type STRING))
   (slot age (type INTEGER)))

(deftemplate classification
   (slot person-name (type STRING))
   (slot category (type SYMBOL)))

(defrule classify-adult
   "Classify a person as an adult if age >= 18"
   (person (name ?name) (age ?age&:(>= ?age 18)))
   =>
   (assert (classification (person-name ?name) (category adult))))
```

### Validation Result

```
Validation: PASSED
Templates: 2
Rules: 1
Warnings: 0
```

## Architecture

```
ruler/
├── rust/
│   ├── src/main.rs         # CLI entry point
│   └── Cargo.toml
├── go/
│   ├── cmd/main.go         # CLI entry point
│   ├── generator.go        # Rule generation logic
│   ├── validator.go        # CLIPS validation
│   └── go.mod
└── shared/
    └── examples/           # Built-in examples
```

## Retry Logic

When generated code fails validation:

1. Parse the validation error
2. Include error context in retry prompt
3. Adjust complexity hints if needed
4. Retry up to N times (default: 5)
5. Return best attempt if all retries fail

## Notes

- CLIPS functionality uses ClipsProvider for validation
- LLM approach requires API key (ANTHROPIC_API_KEY or OPENAI_API_KEY)
- Generated code quality depends on description clarity

## Testing

```bash
# Rust
cd examples/apps/ruler/rust
cargo test

# Go
cd examples/apps/ruler/go
go test -v ./...
```

## License

Part of the nxusKit project.
