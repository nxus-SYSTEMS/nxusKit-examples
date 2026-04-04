# CLIPS+LLM Hybrid Integration

Demonstrates combining CLIPS expert system with LLM for deterministic business rules plus natural language understanding.

> Combine deterministic CLIPS rules with LLM reasoning to build AI pipelines that are both fluent and auditable.

## Edition

**Community** — runs on the OSS / Community SDK edition.

## CLIPS integration path

The CLIPS stage uses **provider chat** (JSON `ClipsInput` in the user message, `ClipsOutput` in `content`). See `go/clips_wire.go` and Rust crate `examples/shared/clips-wire-rust`. For **Session API** usage, use the CLIPS session bindings in your language SDK instead.

Schema: `conformance/clips-json-contract.json`. Documentation: nxusKit SDK `sdk-packaging/docs/rule-authoring.md` — **ClipsInput JSON Reference** (`#clipsinput-json-reference`; bundle: `docs/rule-authoring.md`).

## What this demonstrates

**Difficulty: Intermediate** 🟦 · LLM · CLIPS

- **Summary:** Hybrid CLIPS rules + LLM reasoning
- **Scenario:** Combine deterministic CLIPS rules with LLM-based reasoning
- **`tech_tags` in manifest:** `CLIPS, LLM` — example id **`clips-llm-hybrid`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **Models:** Set cloud provider API keys and/or run **Ollama** locally when you execute the **Run** steps (interactive flags like `--help` / `--verbose` are documented below).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## Key nxusKit Features Demonstrated

| Feature | Description | Rust | Go |
|---------|-------------|------|-----|
| **ClipsProvider** | Rule-based expert system as LLMProvider | ✅ `ClipsProvider::builder()` | ✅ `NewClipsProvider()` |
| **JSON Fact Assertion** | Convert structured data to CLIPS facts | ✅ `ChatRequest` with JSON | ✅ `ChatRequest` with JSON |
| **Conclusion Extraction** | Parse CLIPS output for derived facts | ✅ `ClipsOutput::conclusions` | ✅ `ClipsOutput.Conclusions` |
| **Provider Abstraction** | Same interface for LLM and CLIPS | ✅ `LLMProvider` trait | ✅ `LLMProvider` interface |
| **ResponseFormat** | Structured JSON output from LLM | ✅ `ResponseFormat::Json` | ✅ `JSONMode: true` |
| **Hybrid Pipeline** | LLM → CLIPS → LLM workflow | ✅ `analyze_ticket()` | ✅ `AnalyzeTicket()` |

## Real-World Application

Explainable AI decisions, regulated industry automation.

## Technologies

CLIPS, LLM

## Overview

This example shows the "hybrid AI" pattern: using LLM for natural language understanding and CLIPS for deterministic business decisions. Both Rust and Go implementations use the **real ClipsProvider** to execute CLIPS rules.

## Why Hybrid?

| Approach | Strengths | Weaknesses |
|----------|-----------|------------|
| **LLM only** | Natural language understanding, flexibility | Inconsistent policy application, no audit trail |
| **CLIPS only** | Deterministic, auditable, policy-compliant | Can't understand unstructured text |
| **Hybrid** | Both! Understanding AND compliance | More complex architecture |

## Three-Step Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Step 1    │     │   Step 2    │     │   Step 3    │
│     LLM     │ ──► │    CLIPS    │ ──► │     LLM     │
│ (classify)  │     │  (routing)  │     │ (response)  │
└─────────────┘     └─────────────┘     └─────────────┘
    Extract          Apply rules         Generate
   category,        deterministic       empathetic
   priority,        team routing,       customer
   sentiment        SLA, escalation     response
```

1. **LLM Classification**: Extract category, priority, sentiment, entities from ticket text
2. **CLIPS Routing**: Apply deterministic rules for team assignment, SLA, escalation
3. **LLM Response**: Generate appropriate customer response

## Routing Rules

The CLIPS rules in `ticket-routing.clp` apply:

| Category | Priority | Team | SLA | Escalation |
|----------|----------|------|-----|------------|
| Security | Any | Security | 4h | Level 2 |
| Infrastructure | Critical | SRE | 2h | Level 1 |
| Infrastructure | High | SRE | 4h | Level 1 |
| Application | Critical | Development | 4h | Level 1 |
| Application | High | Development | 8h | None |
| General | Any | General Support | 24h | None |

## Library usage

### Rust (with ClipsProvider)

```rust
use clips_llm_hybrid::analyze_ticket;
use std::path::Path;

// nxusKit: Hybrid analysis using LLM + ClipsProvider
let rules_path = Path::new("ticket-routing.clp");
let result = analyze_ticket(&provider, "llama3", ticket_text, rules_path).await?;

// Deterministic routing from CLIPS (auditable, explainable)
println!("Team: {}", result.team);
println!("SLA: {} hours", result.sla_hours);

// LLM-derived insights (natural language understanding)
println!("Sentiment: {}", result.sentiment);
println!("Response: {}", result.suggested_response);
```

### Go (with ClipsProvider)

```go
// nxusKit: Hybrid analysis using LLM + ClipsProvider
rulesPath := "ticket-routing.clp"
result, err := AnalyzeTicket(ctx, provider, "llama3", ticketText, rulesPath)

// Deterministic routing from CLIPS (auditable, explainable)
fmt.Println("Team:", result.Team)
fmt.Println("SLA:", result.SLAHours, "hours")

// LLM-derived insights (natural language understanding)
fmt.Println("Sentiment:", result.Sentiment)
```

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/clips-llm-hybrid`:
cd rust && cargo build
cd go && make build
```

## Run

### Rust
```bash
cd rust
cargo run
```

### Go
```bash
cd go
go run .
```

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
go run . --verbose          # Go

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
go run . --step             # Go

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## CLIPS Rules File

See `ticket-routing.clp` for the actual CLIPS rules used in the Rust implementation.

## Testing

```bash
# Rust
cd rust && cargo test

# Go
cd go && go test -v
```

## Production Considerations

1. **Rule versioning**: Track changes to CLIPS rules with version control
2. **Audit logging**: Log all routing decisions with rule traces
3. **Fallback handling**: Define default routing for edge cases
4. **Rule testing**: Unit test CLIPS rules independently of LLM
5. **Performance**: Cache common routing patterns
