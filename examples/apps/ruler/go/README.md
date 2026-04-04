# Ruler - CLIPS Rule Generation (Go)

An LLM-powered tool that generates valid CLIPS rules from natural language descriptions, with automatic validation and retry.

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

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## Overview

The Ruler uses an LLM to translate natural language rule descriptions into CLIPS code, then validates the generated code using the CLIPS parser. If validation fails, it retries with error feedback.

## Features

### Complexity Levels

| Level | Constructs Allowed | Use Case |
|-------|-------------------|----------|
| `basic` | deftemplate, defrule (simple patterns) | Simple classification rules |
| `intermediate` | + salience, test, constraints | Business logic |
| `advanced` | + deffunction, defmodule | Complex expert systems |

### Validation

Generated code is validated for:
- Balanced parentheses
- Valid CLIPS syntax
- No dangerous constructs (system, exec, etc.)
- Template existence
- Slot type correctness

### Retry with Feedback

When validation fails, the LLM receives error feedback:
```
PREVIOUS ATTEMPT HAD THESE ERRORS - please fix them:
- Unbalanced parentheses at line 15
- Unknown slot 'ages' in template 'person'
```

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/ruler/go`:
cd ../rust && cargo build
make build
```

## Run

### Generate Classification Rules

```bash
cd packages/nxuskit-go/examples/ruler

go run ./cmd/ruler generate \
  --description "Classify a person as senior if age >= 65, adult if age >= 18, otherwise minor" \
  --complexity basic \
  --output rules/age-classification.clp
```

### Generate Business Rules

```bash
go run ./cmd/ruler generate \
  --description "If order total > 100 and customer is premium, apply 10% discount" \
  --complexity intermediate \
  --output rules/discount-rules.clp
```

### Generate with Domain Hints

```bash
go run ./cmd/ruler generate \
  --description "Route support tickets to appropriate queues" \
  --complexity intermediate \
  --domain-hints "ticket,queue,priority,category" \
  --output rules/ticket-routing.clp
```

### Validate Existing Rules

```bash
go run ./cmd/ruler validate \
  --input rules/my-rules.clp
```

## Output Example

Generated `age-classification.clp`:
```clips
;;; Age Classification Rules
;;; Generated from: "Classify a person as senior if age >= 65..."

(deftemplate person
   (slot name (type STRING))
   (slot age (type INTEGER)))

(deftemplate classification
   (slot name (type STRING))
   (slot category (type SYMBOL)))

(defrule classify-senior
   (person (name ?n) (age ?a&:(>= ?a 65)))
   =>
   (assert (classification (name ?n) (category senior))))

(defrule classify-adult
   (person (name ?n) (age ?a&:(and (>= ?a 18) (< ?a 65))))
   =>
   (assert (classification (name ?n) (category adult))))

(defrule classify-minor
   (person (name ?n) (age ?a&:(< ?a 18)))
   =>
   (assert (classification (name ?n) (category minor))))
```

## Generation Result

```json
{
  "success": true,
  "attempts": 1,
  "rules": {
    "id": "age-classification",
    "code": "...",
    "model": "llama3.2",
    "tokens_used": 450,
    "generation_time_ms": 2340
  },
  "validation": {
    "valid": true,
    "templates": ["person", "classification"],
    "rules": ["classify-senior", "classify-adult", "classify-minor"]
  }
}
```

## Configuration Options

| Flag | Description | Default |
|------|-------------|---------|
| `--max-retries` | Maximum generation attempts | 5 |
| `--timeout` | Timeout per attempt | 30s |
| `--temperature` | LLM temperature | 0.2 |
| `--model` | Specific model to use | (provider default) |

## LLM Provider Configuration

```bash
export LLMKIT_PROVIDER_SEQUENCE="ollama,claude,openai"
```

## Running Tests

```bash
go test -v ./...
```

## CLIPS Feature

For CLIPS validation using ClipsProvider:
```bash
go build -tags clips ./...
```

This enables CLIPS-based rule syntax validation.
