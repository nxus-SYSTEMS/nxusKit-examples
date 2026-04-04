# Multi-Provider Pipeline -- BN -> Solver -> CLIPS

Demonstrates the flagship nxusKit integration pattern: chaining Bayesian Network prediction, constraint solver optimization, and CLIPS rule-based safety enforcement in a 3-stage pipeline. Each stage feeds its output into the next, showing how probabilistic, combinatorial, and symbolic reasoning compose through a unified SDK.

> Chain probabilistic prediction, constraint optimization, and rule-based safety enforcement into a single production-ready pipeline using one unified SDK.

**Scenarios**: `festival` · `rescue` · `bakery`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## CLIPS integration path (stage 3)

Stage 3 is **CLIPS**: the **Go** path uses **provider chat** (`go/clips_wire.go`, `ClipsInput` / `ClipsOutput` JSON in the chat API). The **Rust** path uses the **Session API** (`nxuskit::clips::ClipsSession` — load rules, `fact_assert_structured`, `run`). Use the path that matches your integration style; both enforce the same rule files.

Schema: `conformance/clips-json-contract.json`. Docs: nxusKit SDK `sdk-packaging/docs/rule-authoring.md` — **ClipsInput JSON Reference** (`#clipsinput-json-reference`; bundle: `docs/rule-authoring.md`).

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · CLIPS · Solver · BN

- **Summary:** Three-stage BN prediction → Solver optimization → CLIPS safety pipeline
- **Scenario:** Chain Bayesian Network prediction into Solver optimization with CLIPS safety enforcement
- **`tech_tags` in manifest:** `BN, Solver, CLIPS` — example id **`bn-solver-clips-pipeline`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Key nxusKit Features Demonstrated

| Feature | Description | Rust | Go |
|---------|-------------|------|-----|
| **BnNetwork** | Load and query Bayesian Network from BIF file | `BnNetwork::from_bif()` | `LoadBnNetwork()` |
| **BnEvidence** | Set observed evidence for inference | `evidence.set_discrete()` | `ev.SetDiscrete()` |
| **Variable Elimination** | Exact posterior inference algorithm | `net.infer(&ev, "ve")` | `net.Infer(ev, "ve")` |
| **SolverSession** | Create and configure Z3 constraint solver | `SolverSession::new()` | `NewSolverSession()` |
| **Constraint Optimization** | Single-objective optimization with constraints | `session.solve()` | `session.Solve()` |
| **CLIPS (stage 3)** | Rule engine for safety | **`ClipsSession`**: `load_file`, `fact_assert_structured`, `run` | **Provider chat**: `NewClipsProvider()`, JSON in `ChatRequest` |
| **Fact assertion** | Solver → CLIPS | Structured slots → `fact_assert_structured` | JSON facts in user message |
| **Alert / conclusion readout** | Derived template facts | `facts_by_template` + `fact_slot_values` | Parse `ClipsOutput.conclusions` |
| **Pipeline Composition** | 3-stage data flow across provider types | Stage 1 -> 2 -> 3 | Stage 1 -> 2 -> 3 |

## Technologies

Solver, BN

## Pipeline Architecture

```
┌─────────────┐    Posteriors    ┌──────────────┐    Assignments    ┌───────────────┐
│  BN Network  │ ──────────────> │    Solver     │ ──────────────> │  CLIPS Rules  │
│ (Prediction) │                 │ (Optimization)│                 │   (Safety)    │
└─────────────┘                  └──────────────┘                  └───────────────┘
    model.bif                      problem.json                      rules.clp
    evidence.json
```

**Stage 1 -- BN Prediction**: Loads a Bayesian Network from a BIF file, sets observed evidence, and runs Variable Elimination to compute posterior distributions over a target variable (crowd size, survivor probability, or demand level).

**Stage 2 -- Solver Optimization**: Uses the BN prediction to inform a Z3 constraint optimization problem. Variables, constraints, and objectives are loaded from `problem.json`. The solver finds optimal assignments (band-to-stage, team-to-zone, or item-to-oven mappings).

**Stage 3 -- CLIPS Safety Enforcement**: Converts solver assignments into CLIPS facts and asserts them into a rule engine loaded with domain-specific safety rules. The engine fires rules to detect violations and generates typed alerts (critical, warning, info).

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/bn-solver-clips-pipeline`:
cd rust && cargo build
cd go && make build
```

## Run

### Rust

```bash
cd rust
cargo run -- --scenario festival
cargo run -- --scenario rescue --verbose
cargo run -- --scenario bakery --step
```

### Go

```bash
cd go
make build
./bin/bn-solver-clips-pipeline --scenario festival
./bin/bn-solver-clips-pipeline --scenario rescue --verbose
./bin/bn-solver-clips-pipeline --scenario bakery --step
```

Or directly:

```bash
cd go
go run . --scenario festival
```

## Scenarios

### Festival (Music Festival Stage Planning)

A music festival needs to assign bands to stages while maximizing audience enjoyment. The BN predicts crowd size from weather, headliner popularity, and time of day. The solver optimizes band-to-stage assignments. CLIPS rules enforce noise limits and pyrotechnic safety regulations.

- **BN predicts**: `crowd_size` given weather, headliner popularity, time of day
- **Solver optimizes**: band-to-stage assignments maximizing `total_enjoyment`
- **CLIPS enforces**: noise proximity limits, pyrotechnic material restrictions

### Rescue (Search and Rescue Operation)

A disaster response team must deploy rescue units across zones. The BN estimates survivor probability from building damage, time since event, and weather conditions. The solver assigns teams to zones to maximize rescues. CLIPS rules enforce operational safety protocols.

- **BN predicts**: `survivor_probability` given building damage, hours since event, weather
- **Solver optimizes**: team-to-zone assignments maximizing `total_survivors_rescued`
- **CLIPS enforces**: helicopter wind limits, team deployment protocols

### Bakery (Production Scheduling)

A bakery plans its daily production across multiple ovens. The BN forecasts demand level from day of week, season, and local events. The solver schedules items across ovens to minimize waste. CLIPS rules enforce allergen isolation and food safety regulations.

- **BN predicts**: `demand_level` given day of week, season, local events
- **Solver optimizes**: item-to-oven assignments minimizing `total_waste`
- **CLIPS enforces**: allergen cross-contamination, gluten-free isolation, scheduling conflicts

## Interactive Modes

All examples support debugging flags for inspecting pipeline internals:

```bash
# Verbose mode - show intermediate data, network variables, fact assertions, rule traces
cargo run -- --scenario festival --verbose      # Rust
go run . --scenario festival --verbose          # Go

# Step mode - pause at each pipeline stage with explanations
cargo run -- --scenario rescue --step           # Rust
go run . --scenario rescue --step               # Go

# Combined mode
cargo run -- --scenario bakery --verbose --step
go run . --scenario bakery --verbose --step
```

Or use environment variables:

```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Scenario Data Format

Each scenario directory contains four files:

| File | Purpose | Consumed By |
|------|---------|-------------|
| `model.bif` | Bayesian Network definition in BIF format (variables, parents, CPTs) | Stage 1: BnNetwork |
| `evidence.json` | Observed variable values as `{"variable": "state"}` pairs | Stage 1: BnEvidence |
| `problem.json` | Solver problem with variables, constraints, and objectives | Stage 2: SolverSession |
| `rules.clp` | CLIPS rule definitions for domain-specific safety checks | Stage 3: ClipsProvider |
| `expected-output.json` | Golden output describing expected pipeline results | Testing/validation |

### Adding a New Scenario

1. Create a new directory under `scenarios/`
2. Define the BN model in `model.bif` with evidence and prediction variables
3. Create `evidence.json` with the observed evidence
4. Define the optimization problem in `problem.json`
5. Write CLIPS safety rules in `rules.clp` with appropriate templates
6. Add the scenario's CLIPS template mapping to `knownScenarios` in the source code
7. Create `expected-output.json` with the expected pipeline results

## Real-World Applications

This pipeline pattern maps directly to operational decision-making systems:

- **Event planning**: Predict attendance, optimize resource allocation, enforce safety codes
- **Emergency response**: Estimate survival windows, deploy rescue assets, enforce operational protocols
- **Manufacturing**: Forecast demand, schedule production, enforce quality and safety standards
- **Logistics**: Predict delivery volumes, optimize fleet routing, enforce regulatory compliance
- **Healthcare**: Predict patient load, optimize staff scheduling, enforce clinical safety protocols

The key insight is that each stage addresses a fundamentally different reasoning task -- probabilistic prediction, combinatorial optimization, and rule-based compliance -- and nxusKit provides a unified interface for composing all three.

## Testing

```bash
# Rust
cd rust && cargo test

# Go
cd go && go test -v
```

Each scenario includes an `expected-output.json` that describes the expected structure of the pipeline results, useful for regression testing and validation.
