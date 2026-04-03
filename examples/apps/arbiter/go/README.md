# Arbiter - LLM Validation Loop (Go)

A validation framework that uses CLIPS rules to validate LLM outputs and auto-retry with parameter adjustments when validation fails.

> Stop accepting unreliable LLM output — validate every response against CLIPS rules and retry automatically until your standards are met.

**Scenarios**: `classification` · `extraction` · `reasoning`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** 🏁 · LLM · CLIPS

- **Summary:** CLIPS-validated LLM retry app with rule-based answer verification
- **Scenario:** Submit questions to an LLM and validate answers against CLIPS rules, retrying on validation failure
- **`tech_tags` in manifest:** `CLIPS, LLM` — example id **`arbiter`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Overview

The Arbiter implements a feedback loop pattern:

1. **LLM Call** - Get initial response from LLM
2. **CLIPS Validation** - Validate response against rules
3. **Failure Detection** - Identify what went wrong
4. **Parameter Adjustment** - Modify LLM parameters based on failure type
5. **Retry** - Make another attempt with adjusted parameters

## Features

### Failure Detection

The CLIPS validator detects various failure types:

| Failure Type | Description | Suggested Adjustment |
|--------------|-------------|---------------------|
| `low_confidence` | Confidence below threshold | Increase temperature |
| `invalid_category` | Category not in allowed set | Add explicit constraints |
| `missing_reasoning` | No reasoning provided | Request detailed explanation |
| `incomplete_extraction` | Fields missing from output | Prompt for all required fields |
| `inconsistent_data` | Contradictory information | Lower temperature |
| `parse_error` | Can't parse JSON response | Simplify output format |

### Parameter Adjustments

Strategies automatically adjust LLM parameters:

```json
{
  "strategy_name": "increase_temperature",
  "failure_type": "low_confidence",
  "adjustments": [
    {"parameter": "temperature", "action": "delta", "value": 0.2}
  ]
}
```

### Configuration

```json
{
  "max_retries": 5,
  "timeout_ms": 30000,
  "initial_temperature": 0.7,
  "rules_dir": "./rules/validation"
}
```

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/arbiter/go`:
cd ../rust && cargo build
make build
```

## Run

### Classification Task

```bash
cd packages/nxuskit-go/examples/solver

go run ./cmd/arbiter classify \
  --input "The patient has fever of 102°F and persistent cough" \
  --categories "urgent,routine,emergency" \
  --max-retries 3
```

### Extraction Task

```bash
go run ./cmd/arbiter extract \
  --input "John Doe, 35, lives at 123 Main St" \
  --schema testdata/person_schema.json \
  --max-retries 5
```

### Custom Validation Rules

```bash
go run ./cmd/arbiter classify \
  --input "Sample input text" \
  --categories "a,b,c" \
  --rules-dir ./custom-rules
```

## Output Example

```json
{
  "task_type": "classification",
  "attempts": 2,
  "final_result": {
    "category": "urgent",
    "confidence": 0.92,
    "reasoning": "High fever combined with respiratory symptoms"
  },
  "validation": {
    "valid": true,
    "rules_fired": ["confidence-threshold", "category-validation"]
  },
  "retry_history": [
    {
      "attempt": 1,
      "failure": "low_confidence",
      "adjustment": "temperature: 0.5 → 0.7",
      "response": {"category": "urgent", "confidence": 0.65}
    }
  ]
}
```

## Writing Validation Rules

CLIPS rules for validation use templates:

```clips
(deftemplate llm-response
   (slot category (type SYMBOL))
   (slot confidence (type FLOAT))
   (slot reasoning (type STRING)))

(deftemplate validation-result
   (slot status (type SYMBOL)) ; valid, invalid, retry
   (slot failure-type (type SYMBOL))
   (slot suggested-adjustment (type STRING)))

(defrule check-confidence
   (llm-response (confidence ?c&:(< ?c 0.7)))
   =>
   (assert (validation-result
      (status retry)
      (failure-type low_confidence)
      (suggested-adjustment "increase temperature"))))
```

## LLM Provider Configuration

```bash
export LLMKIT_PROVIDER_SEQUENCE="ollama,claude,openai"
```

## Running Tests

```bash
go test -v ./...
```

## CLIPS Feature

For real CLIPS validation (using ClipsProvider):
```bash
go build -tags clips ./...
```

This enables the RealClipsValidator in `clips_validator.go`.
