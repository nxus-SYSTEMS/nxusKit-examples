# Bayesian Inference Pattern

Demonstrates Bayesian Network inference using multiple algorithms: load a BIF model, set observed evidence, and compute posterior probability distributions over unobserved variables using exact and approximate methods.

> Run exact and approximate Bayesian inference on real-world diagnostic models using four algorithms and three themed scenarios — all from a single SDK call.

**Scenarios**: `haunted-house` · `coffee-shop` · `plant-doctor`

## Edition

**Community** — runs on the OSS / Community SDK edition.

## What this demonstrates

**Difficulty: Starter** 🟢 · BN

- **Summary:** Bayesian network inference via nxusKit SDK
- **Scenario:** Build a Bayesian network and perform probabilistic inference
- **`tech_tags` in manifest:** `BN` — example id **`bayesian-inference`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, python, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Key nxusKit Features Demonstrated

| Feature | Description |
|---------|-------------|
| **BIF Model Loading** | Parse Bayesian Interchange Format files into a directed acyclic graph with conditional probability tables |
| **Evidence Setting** | Clamp observed variables to known values before inference |
| **Variable Elimination (VE)** | Exact inference by marginalizing out variables in an optimal elimination order |
| **Junction Tree (JT)** | Exact inference via clique tree message passing with global consistency |
| **Loopy Belief Propagation (LBP)** | Approximate inference via iterative message passing on the factor graph |
| **Gibbs Sampling** | Approximate MCMC inference by sampling each variable conditioned on its Markov blanket |
| **Streaming Results** | Progressive output of posteriors as each algorithm step completes |
| **Algorithm Comparison** | Side-by-side comparison of exact and approximate posteriors with tolerance checking |

**Provider Compatibility**: Uses the nxusKit Bayesian Network provider (no LLM provider required)

## Technologies

BN

## Pattern Overview

Many real-world diagnosis and prediction problems can be modeled as Bayesian Networks -- directed acyclic graphs where nodes represent random variables and edges encode conditional dependencies. Given partial observations (evidence), inference computes updated beliefs (posteriors) about unobserved variables. This pattern walks through four inference algorithms on scenario-driven models loaded from BIF files, comparing exact and approximate results.

## Scenarios

Three themed scenarios are included under `scenarios/`:

- **Haunted House** -- Investigate a supposedly haunted house by observing cold spots, flickering lights, and muddy footprints, then infer the probability of a ghost, raccoon, wiring fault, and cold draft. 8 variables, 8 CPTs.
- **Coffee Shop** -- Diagnose a bad espresso shot by observing bitter taste, no sourness, and no wateriness, then infer extraction level, grind size, water temperature, bean age, and freshness. 8 variables, 8 CPTs.
- **Plant Doctor** -- Diagnose a sick plant by observing yellow leaves, wilting, no spots, and slow growth, then infer overwatering, nutrient deficiency, sunlight issues, disease, and pest infestation. 9 variables, 9 CPTs.

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/patterns/bayesian-inference`:
cd rust && cargo build
cd go && make build
cd python && python3 main.py --help
```

## Run

### Rust
```bash
cd rust
cargo run -- --scenario haunted-house
cargo run -- --scenario coffee-shop --verbose
cargo run -- --scenario plant-doctor --step
```

### Go
```bash
cd go
make build
./bin/bayesian-inference --scenario haunted-house
./bin/bayesian-inference --scenario coffee-shop --verbose
./bin/bayesian-inference --scenario plant-doctor --step
```

### Python
```bash
cd python
pip install -e ../../../../packages/nxuskit-py   # if not already installed
python main.py --scenario haunted-house
python main.py --scenario coffee-shop --step
```

## Inference Steps

Each run progresses through four algorithm steps:

| Step | Algorithm | Type | What It Does |
|------|-----------|------|--------------|
| 1 | **Variable Elimination** | Exact | Eliminates variables one at a time, computing exact marginal posteriors via factor multiplication and summation |
| 2 | **Junction Tree** | Exact | Builds a clique tree from the model, propagates messages for globally consistent exact posteriors |
| 3 | **Loopy Belief Propagation** | Approximate | Passes messages iteratively on the factor graph until convergence (or max iterations) |
| 4 | **Gibbs Sampling** | Approximate | Draws MCMC samples from the posterior, estimating marginals from sample frequencies |

## Scenario Data Format

Each scenario is a directory containing two files:

### `model.bif` -- Bayesian Interchange Format

Defines the network structure, variable domains, and conditional probability tables:

```bif
network unknown {
}

variable ghost {
  type discrete [ 2 ] { yes, no };
}

variable cold_spots {
  type discrete [ 2 ] { yes, no };
}

probability ( ghost ) {
  table 0.05, 0.95;
}

probability ( cold_spots | ghost, cold_draft ) {
  (yes, yes) 0.9, 0.1;
  (yes, no)  0.8, 0.2;
  (no, yes)  0.6, 0.4;
  (no, no)   0.05, 0.95;
}
```

### `evidence.json` -- Observed Variables

Maps variable names to their observed values:

```json
{
    "cold_spots": "yes",
    "flickering_lights": "yes",
    "footprints": "muddy"
}
```

### `expected-output.json` -- Golden Output

Contains exact posteriors from VE/JT and tolerance bounds for LBP/Gibbs, plus qualitative observations about the inference results. Used for automated validation of implementation correctness.

## Algorithm Comparison

| Property | Variable Elimination | Junction Tree | Loopy BP | Gibbs Sampling |
|----------|---------------------|---------------|----------|----------------|
| **Type** | Exact | Exact | Approximate | Approximate |
| **Method** | Factor marginalization | Clique tree message passing | Iterative factor graph messages | MCMC sampling |
| **Guarantees** | Exact posteriors | Exact posteriors | No convergence guarantee on loopy graphs | Converges asymptotically |
| **Speed** | Fast for small networks | Fast after tree construction | Fast per iteration, may need many | Slow (many samples needed) |
| **Memory** | Exponential in treewidth | Exponential in max clique size | Linear in edges | Linear in variables |
| **Best For** | Small-medium networks | Repeated queries on same model | Large networks with weak loops | Complex models, posterior samples |
| **Parameters** | Elimination order | None (automatic) | Max iterations, damping factor | Num samples, burn-in, seed |

VE and JT should produce identical posteriors (both are exact). LBP and Gibbs posteriors should fall within the tolerance bounds specified in `expected-output.json`.

## Real-World Applications

| Application | How this example applies |
|-------------|--------------------------|
| Haunted House | Fault diagnosis, anomaly detection, sensor fusion from multiple noisy sensors pointing to hidden causes |
| Coffee Shop | Manufacturing quality control, process parameter tuning, root cause analysis in production |
| Plant Doctor | Medical diagnosis, agricultural advisory systems, multi-symptom differential diagnosis |

## Interactive Modes

All implementations support debugging flags:

```bash
# Verbose mode - show CPTs, elimination orders, message schedules, and sample traces
cargo run -- --scenario haunted-house --verbose      # Rust
./bin/bayesian-inference --scenario haunted-house --verbose  # Go
python main.py --scenario haunted-house --verbose     # Python

# Step mode - pause at each algorithm with explanations
cargo run -- --scenario haunted-house --step          # Rust
./bin/bayesian-inference --scenario haunted-house --step     # Go
python main.py --scenario haunted-house --step        # Python

# Combined mode
cargo run -- --scenario haunted-house --verbose --step
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

1. **Algorithm selection**: Use VE or JT for small-to-medium networks where exact inference is tractable. Switch to LBP or Gibbs for large networks where treewidth makes exact inference infeasible.
2. **Convergence monitoring**: LBP may not converge on graphs with strong loops. Monitor message deltas and set a maximum iteration count.
3. **Sample size tuning**: For Gibbs sampling, increase `num_samples` and `burn_in` for tighter posterior estimates. Use a fixed seed for reproducibility in testing.
4. **Evidence validation**: Verify that evidence variable names and values match the BIF model before running inference. Mismatched evidence silently produces incorrect posteriors.
