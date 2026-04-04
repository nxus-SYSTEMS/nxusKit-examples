# Solver Pattern

Demonstrates the full solver lifecycle: satisfaction checking, single- and multi-objective optimization, soft constraints, and what-if analysis using push/pop scoping.

> Define variables, add constraints, and solve complex planning problems with Z3 — without leaving your nxusKit workflow.

**Scenarios**: `theme-park` · `space-colony` · `fantasy-draft`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Intermediate** 🟦 · Solver

- **Summary:** Z3 constraint solver integration via nxusKit SDK
- **Scenario:** Define and solve constraint satisfaction problems with Z3
- **`tech_tags` in manifest:** `Solver` — example id **`solver`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, python, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Key nxusKit Features Demonstrated

| Feature | Description |
|---------|-------------|
| **SolverSession Lifecycle** | Create, build model incrementally, solve, and close via the nxuskit SDK |
| **Variable & Constraint Model** | Define typed variables with domains and add hard/soft constraints |
| **Satisfaction Solving** | Check feasibility before optimizing |
| **Single & Multi-Objective Optimization** | Maximize/minimize one or many weighted objectives |
| **Soft Constraints** | Weighted preferences the solver satisfies when possible |
| **Push/Pop Scoping** | Reversible what-if analysis without rebuilding the model |

**Provider Compatibility**: Uses the nxusKit Z3-based constraint solver (no LLM provider required)

## Technologies

Solver

## Pattern Overview

Many real-world planning problems require finding valid assignments to decision variables that satisfy a set of constraints, then optimizing one or more objectives. This pattern walks through five progressive solver steps using scenario-driven problem definitions loaded from JSON files.

## Scenarios

Three themed scenarios are included under `scenarios/`:

- **Theme Park Planning** -- Decide how many rides to build, staff to hire, land to allocate, and ticket prices to set while staying within budget and space constraints. Objectives: maximize rides, minimize budget.
- **Space Colony Planning** -- Design a self-sustaining colony by balancing population against habitat modules, solar panels, water recyclers, and food domes. What-if: simulate a solar storm that degrades panel efficiency by 30%.
- **Fantasy Sports Draft** -- Build an optimal roster under a $50,000 salary cap by selecting stats across QB, RB, WR, TE, and DEF positions to maximize total fantasy points. What-if: simulate key player injuries.

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/patterns/solver`:
cd rust && cargo build
cd go && make build
cd python && python3 main.py --help
```

## Run

### Rust
```bash
cd rust
cargo run -- --scenario theme-park
cargo run -- --scenario space-colony --verbose
cargo run -- --scenario fantasy-draft --step
```

### Go
```bash
cd go
make build
./bin/solver --scenario theme-park
./bin/solver --scenario space-colony --verbose
./bin/solver --scenario fantasy-draft --step
```

### Python
```bash
cd python
pip install -e ../../../../packages/nxuskit-py   # if not already installed
python main.py --scenario theme-park
python main.py --scenario fantasy-draft --step
```

## Solver Steps

Each run progresses through five steps (steps are skipped when a scenario lacks the relevant definitions):

| Step | Name | What It Does |
|------|------|--------------|
| 1 | **Satisfaction** | Adds hard constraints and checks whether any feasible assignment exists (`sat` / `unsat`) |
| 2 | **Optimization** | Sets a single objective (maximize or minimize) and finds the optimal assignment |
| 3 | **Multi-objective** | Combines multiple objectives with weights into a single weighted optimization |
| 4 | **Soft constraints** | Adds weighted preference constraints the solver may violate if necessary |
| 5 | **What-if analysis** | Uses `push` / `pop` to temporarily add constraints, solve, then restore the base model |

## Scenario Data Format

Each scenario is a directory containing a `problem.json` file with the following structure:

```jsonc
{
  "name": "Scenario Name",
  "description": "Human-readable description of the planning problem.",

  "variables": [
    {
      "name": "budget",
      "var_type": "integer",          // "integer", "real", or "boolean"
      "domain": { "min": 50000, "max": 500000 },  // omitted for booleans
      "label": "Total budget in dollars"
    }
  ],

  "constraints": [
    {
      "name": "cost_constraint",
      "constraint_type": "ge",        // "ge", "le", "eq", etc.
      "variables": ["budget", "ride_count"],
      "parameters": {},               // solver-specific parameters
      "expression": "budget >= ride_count * 25000",  // human-readable
      "label": "Cost constraint"
    }
  ],

  "soft_constraints": [
    // Same structure as constraints, with an additional "weight" field
    { "weight": 5.0, "..." : "..." }
  ],

  "objectives": [
    {
      "name": "maximize_rides",
      "direction": "maximize",        // "maximize" or "minimize"
      "expression": "ride_count",
      "variable": "ride_count",       // primary variable for simple objectives
      "weight": 1.0,                  // relative weight for multi-objective
      "priority": 1,                  // priority ordering
      "label": "Maximize the number of rides"
    }
  ],

  "what_if_scenarios": [
    {
      "name": "Add Roller Coaster",
      "description": "What happens if we commit to a roller coaster?",
      "additional_constraints": [
        // Same structure as constraints; added temporarily via push/pop
      ]
    }
  ]
}
```

## Real-World Applications

| Scenario | Real-World Analog |
|----------|-------------------|
| Theme Park Planning | Facility layout, capital budgeting, resource allocation |
| Space Colony Planning | Infrastructure sizing, capacity planning, disaster recovery modeling |
| Fantasy Sports Draft | Portfolio optimization, team composition, auction bidding strategies |

## Interactive Modes

All implementations support debugging flags:

```bash
# Verbose mode - show solver stats, variable details, and intermediate state
cargo run -- --scenario theme-park --verbose      # Rust
./bin/solver --scenario theme-park --verbose  # Go
python main.py --scenario theme-park --verbose     # Python

# Step mode - pause at each phase with explanations
cargo run -- --scenario theme-park --step          # Rust
./bin/solver --scenario theme-park --step     # Go
python main.py --scenario theme-park --step        # Python

# Combined mode
cargo run -- --scenario theme-park --verbose --step
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

# Python
cd python && python -m pytest
```

## Production Considerations

1. **Timeout handling**: Set `timeout_ms` in `SolverConfig` to bound solve time on large models
2. **Incremental solving**: Add constraints and re-solve rather than rebuilding from scratch
3. **Soft constraint weights**: Calibrate weights based on domain expertise; higher weights are harder to violate
4. **What-if batching**: Use push/pop for rapid scenario comparison without session recreation
