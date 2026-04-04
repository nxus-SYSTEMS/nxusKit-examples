# Solver What-If Pattern

Demonstrates push/pop scoping, assumption-based solving, and what-if analysis using the nxusKit constraint solver. Each scenario defines a base problem and several what-if variants that temporarily modify the model to explore alternative outcomes.

> Explore alternative outcomes without rebuilding your model — push constraints, solve, compare, and pop back to baseline in one clean pattern.

**Scenarios**: `wedding` · `mars` · `recipe`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Intermediate** 🟦 · Solver

- **Summary:** What-if scenario analysis with solver streaming
- **Scenario:** Stream solver results for interactive what-if scenario exploration
- **`tech_tags` in manifest:** `Solver, Streaming` — example id **`solver-what-if`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust, python (paths under this directory).
- **Models:** Set cloud provider API keys and/or run **Ollama** locally when you execute the **Run** steps (interactive flags like `--help` / `--verbose` are documented below).

## Key nxusKit Features Demonstrated

| Feature | Description |
|---------|-------------|
| **SolverSession Lifecycle** | Create, build model incrementally, solve, and close via the nxuskit SDK |
| **Push/Pop Scoping** | Save and restore model state for reversible experimentation |
| **What-If Analysis** | Add temporary constraints, solve, compare deltas, then restore |
| **Explanation / Unsat Core** | Retrieve constraint labels that cause infeasibility via `Explanation()` |
| **Delta Comparison** | Compare base vs. what-if variable assignments and objective values |

**Provider Compatibility**: Uses the nxusKit Z3-based constraint solver (no LLM provider required)

## Technologies

Solver, Streaming

## Pattern Overview

Real-world planning often involves asking "what if?" -- exploring how changes to assumptions affect the optimal solution. This pattern uses the solver's push/pop mechanism to efficiently evaluate multiple alternative scenarios without rebuilding the model from scratch.

The pipeline for each run:

1. **Load** a problem with base constraints, objective, and what-if scenario definitions
2. **Solve** the base problem to establish a baseline optimal solution
3. **For each what-if scenario**:
   - **Push** the current solver state (saves all constraints and objective)
   - **Add** temporary constraints that define the alternative scenario
   - **Solve** under the modified model
   - If UNSAT, **retrieve explanation** (unsat core labels)
   - **Compare** the what-if result to the baseline (show variable deltas)
   - **Pop** the solver state (restores the base model)
4. **Summarize** all scenarios in a comparison table

## Scenarios

Three themed scenarios are included under `scenarios/`:

- **Wedding Budget Planning** -- Allocate a $25,000 wedding budget across venue, catering, flowers, photography, music, and decor. What-if: splurge on a fancy venue, cut the DJ, or double the budget.
- **Mars Colony Resource Allocation** -- Design a Mars colony by balancing colonists against solar panels, water recyclers, greenhouses, habitats, and power storage under a cargo mass limit. What-if: require 50+ colonists, simulate a dust storm, or get extra cargo capacity.
- **Recipe Scaling** -- Scale a baking recipe by adjusting flour, sugar, eggs, butter, milk, and vanilla while maintaining proper ratios. What-if: limited eggs, go fully vegan (may be UNSAT), or bake for a party.

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/patterns/solver-what-if`:
cd rust && cargo build
cd go && make build
```

## Run

### Rust
```bash
cd rust
cargo run -- --scenario wedding
cargo run -- --scenario mars --verbose
cargo run -- --scenario recipe --step
```

### Go
```bash
cd go
make build
./bin/solver-what-if --scenario wedding
./bin/solver-what-if --scenario mars --verbose
./bin/solver-what-if --scenario recipe --step
```

### Python
```bash
cd python
python3 main.py --scenario wedding
python3 main.py --scenario mars --verbose
python3 main.py --scenario recipe --step
```

## Push/Pop Concepts

The solver's push/pop mechanism works like a stack of model snapshots:

```
Base model: [variables + constraints + objective]
  |
  push()  --> saves state
  |
  add_constraints([temporary constraints])
  solve() --> result under modified model
  |
  pop()   --> restores base model (temporary constraints removed)
```

Key properties:
- **Push** creates a new scope level; all subsequent additions are scoped
- **Pop** removes everything added since the last push
- Multiple push/pop levels can be nested
- The solver does not re-initialize -- it reuses learned information for efficiency

## Unsat Core Explanation

When a what-if scenario makes the model infeasible (UNSAT), the solver can report which constraints are responsible:

1. Enable explanation with `ProduceExplanation: true` in the solve config
2. After an UNSAT result, call `Explanation()` to retrieve the unsat core
3. The `unsat_core_labels` array contains the constraint labels that form a minimal conflicting set

This is particularly useful for understanding *why* a scenario is impossible (e.g., the vegan recipe scenario where eggs=0 conflicts with the eggs-per-flour ratio constraint).

## Scenario Data Format

Each scenario is a directory containing a `problem.json` file:

```jsonc
{
  "name": "Scenario Name",
  "description": "Human-readable description.",

  "variables": [
    {
      "name": "venue_cost",
      "var_type": "integer",
      "domain": { "min": 5000, "max": 15000 },
      "label": "Cost of the venue in dollars"
    }
  ],

  "constraints": [
    {
      "name": "budget_limit",
      "constraint_type": "le",
      "variables": ["venue_cost", "catering_cost"],
      "parameters": { "budget": 25000 },
      "expression": "venue_cost + catering_cost <= 25000",
      "label": "Budget constraint"
    }
  ],

  "objectives": [
    {
      "name": "maximize_total_quality",
      "direction": "maximize",
      "expression": "venue_cost + catering_cost",
      "variable": "venue_cost",
      "weight": 1.0,
      "label": "Maximize total quality"
    }
  ],

  "what_if_scenarios": [
    {
      "name": "fancy_venue",
      "description": "What if we splurge on a fancy venue?",
      "additional_constraints": [
        {
          "name": "fancy_venue_min",
          "constraint_type": "ge",
          "variables": ["venue_cost"],
          "parameters": { "min_value": 12000 },
          "expression": "venue_cost >= 12000",
          "label": "Fancy venue minimum"
        }
      ]
    }
  ]
}
```

## Real-World Applications

| Scenario | Real-World Analog |
|----------|-------------------|
| Wedding Budget Planning | Event planning, capital budgeting, portfolio allocation |
| Mars Colony Planning | Infrastructure sizing, supply chain planning, disaster preparedness |
| Recipe Scaling | Manufacturing scaling, formulation optimization, process engineering |

## Interactive Modes

All implementations support debugging flags:

```bash
# Verbose mode - show solver stats and constraint details
cargo run -- --scenario wedding --verbose      # Rust
./bin/solver-what-if --scenario wedding --verbose  # Go

# Step mode - pause at each phase with explanations
cargo run -- --scenario wedding --step          # Rust
./bin/solver-what-if --scenario wedding --step     # Go

# Combined mode
cargo run -- --scenario wedding --verbose --step
```

Or use environment variables (Rust and Go only):
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Testing

```bash
# Rust
cd rust && cargo test

# Go
cd go && go test -v
```

## Production Considerations

1. **Push/Pop depth**: Keep nesting shallow; deep push/pop stacks add solver overhead
2. **Explanation cost**: Producing unsat cores adds overhead; only enable when needed
3. **Constraint interaction**: What-if constraints are *added* to existing constraints via push, not *replaced*. Design base constraints to be compatible with what-if additions.
4. **Timeout handling**: Set `timeout_ms` in `SolverConfig` to bound solve time on large models
