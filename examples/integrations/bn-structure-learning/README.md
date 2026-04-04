# BN Structure Learning -- Causal Discovery from Data

Demonstrates Bayesian Network structure learning: discovering causal relationships directly from observational CSV data, learning parameters, evaluating model fit, and running inference on the learned model. Two structure learning algorithms (Hill-Climb and K2) are compared to identify high-confidence causal links.

> Discover causal structure hidden in your data — learn Bayesian network topology and parameters directly from CSV observations using Hill-Climb and K2 search algorithms.

**Scenarios**: `golf` · `bmx` · `sourdough`

## Edition

**Community** — runs on the OSS / Community SDK edition.

## What this demonstrates

**Difficulty: Intermediate** 🟦 · BN

- **Summary:** Bayesian network structure learning from data
- **Scenario:** Learn Bayesian network structure from observational data
- **`tech_tags` in manifest:** `BN` — example id **`bn-structure-learning`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Key nxusKit Features Demonstrated

| Feature | Description | Rust | Go |
|---------|-------------|------|-----|
| **BnNetwork (empty)** | Create an empty network for structure learning | `nxuskit_bn_net_create()` | `NewBnNetwork()` |
| **Hill-Climb Search** | Greedy structure search with edge add/remove/reverse | `nxuskit_bn_search_structure(..., "hill_climb", ...)` | `net.SearchStructure(..., "hill_climb")` |
| **K2 Search** | Order-based structure search with variable ordering | `nxuskit_bn_search_structure(..., "k2", ...)` | `net.SearchStructure(..., "k2")` |
| **BIC Scoring** | Bayesian Information Criterion (penalizes complexity) | `scoring = "bic"` | `Scoring: "bic"` |
| **BDeu Scoring** | Bayesian Dirichlet equivalent uniform scoring | `scoring = "bdeu"` | `Scoring: "bdeu"` |
| **MLE Learning** | Maximum Likelihood Estimation for CPT parameters | `nxuskit_bn_learn_mle()` | `net.LearnMLE()` |
| **Log-Likelihood** | Evaluate model fit against training data | `nxuskit_bn_log_likelihood()` | `net.LogLikelihood()` |
| **VE Inference** | Variable Elimination on the learned model | `nxuskit_bn_infer(..., "ve", ...)` | `net.Infer(ev, "ve")` |

## Technologies

BN

## Pipeline Architecture

```
┌───────────┐    Column names    ┌──────────────┐    Learned edges    ┌───────────────┐
│  CSV Data  │ ───────────────> │  Structure    │ ─────────────────> │  Parameter    │
│ (200 rows) │                  │  Learning     │                    │  Learning     │
└───────────┘                   │  (HC / K2)    │                    │  (MLE)        │
                                └──────────────┘                     └───────┬───────┘
                                                                             │
                                     ┌──────────────┐    Fit score    ┌──────┴───────┐
                                     │  Algorithm    │ <───────────── │    Log-       │
                                     │  Comparison   │                │  Likelihood   │
                                     └──────────────┘                └──────┬───────┘
                                                                             │
                                                                      ┌──────┴───────┐
                                                                      │  Inference    │
                                                                      │  (VE)         │
                                                                      └──────────────┘
```

**Step 1 -- Load CSV Data**: Reads the scenario CSV file, discovers column names (which become BN variables) and row count.

**Step 2 -- Hill-Climb + BIC**: Runs greedy structure search starting from an empty graph. At each step, the algorithm tries adding, removing, or reversing an edge, accepting the change that most improves the BIC score. BIC balances fit against model complexity via a log(N) penalty term.

**Step 3 -- K2 + BDeu**: Runs order-based structure search using the CSV column ordering. K2 processes variables in order, greedily adding parent edges that improve the BDeu score. BDeu uses an equivalent sample size (ESS) hyperparameter that controls the strength of the prior.

**Step 4 -- MLE Parameter Learning**: Fits conditional probability tables (CPTs) to the Hill-Climb structure using Maximum Likelihood Estimation with Laplace smoothing (pseudocount=1.0) to avoid zero probabilities.

**Step 5 -- Log-Likelihood Evaluation**: Computes how well the learned model explains the training data. Per-sample log-likelihood allows comparison across different dataset sizes.

**Step 6 -- Inference**: Runs Variable Elimination on the learned model with sample evidence to demonstrate that the learned network supports standard BN queries.

**Step 7 -- Algorithm Comparison**: Compares edges discovered by both algorithms. Shared edges represent high-confidence causal relationships found independently by two different search strategies.

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/bn-structure-learning`:
cd rust && cargo build
cd go && make build
```

## Run

### Rust

```bash
cd rust
cargo run -- --scenario golf
cargo run -- --scenario bmx --verbose
cargo run -- --scenario sourdough --step
```

### Go

```bash
cd go
make build
./bin/bn-structure-learning --scenario golf
./bin/bn-structure-learning --scenario bmx --verbose
./bin/bn-structure-learning --scenario sourdough --step
```

Or directly:

```bash
cd go
go run . --scenario golf
```

## Scenarios

### Golf (Course Conditions)

Models how weather, soil conditions, maintenance practices, and fertilizer affect golf course playing conditions. The data encodes realistic correlations: rainy weather increases soil moisture, which softens fairways; heavy fertilizer increases green speed; longer mowing increases rough thickness.

- **Variables**: weather, soil_moisture, mowing, foot_traffic, fertilizer, green_speed, fairway_firmness, rough_thickness
- **Expected causal links**: weather -> soil_moisture -> fairway_firmness, fertilizer -> green_speed, mowing -> rough_thickness
- **Inference demo**: P(green_speed | weather=rainy, fertilizer=heavy)

### BMX (Rider Performance)

Models how rider skill, technique, and jump characteristics affect BMX race outcomes. High skill correlates with perfect pump timing and fast speed; extreme jumps with low skill dramatically increase crash risk.

- **Variables**: jump_height, berm_angle, pump_timing, speed, skill, lap_time, crash_risk, style_score
- **Expected causal links**: skill -> pump_timing, skill -> jump_height, speed -> lap_time, jump_height + skill -> crash_risk
- **Inference demo**: P(lap_time | skill=pro, pump_timing=perfect)

### Sourdough (Baking)

Models how feeding schedule, flour choice, temperature, and starter maturity affect sourdough bread characteristics. Warm temperatures with mature starters produce fast rises and dense bubbles; rye flour and infrequent feeding lead to sour flavors.

- **Variables**: feeding_schedule, flour_type, ambient_temp, hydration, starter_age, rise_time, bubble_density, flavor_profile
- **Expected causal links**: ambient_temp + starter_age -> rise_time -> bubble_density, flour_type -> flavor_profile, feeding_schedule -> starter_age
- **Inference demo**: P(flavor_profile | flour_type=rye, ambient_temp=warm)

## Interactive Modes

```bash
# Verbose mode -- show raw JSON results and intermediate data
cargo run -- --scenario golf --verbose      # Rust
go run . --scenario golf --verbose          # Go

# Step mode -- pause at each step with explanations
cargo run -- --scenario bmx --step          # Rust
go run . --scenario bmx --step              # Go

# Combined mode
cargo run -- --scenario sourdough --verbose --step
go run . --scenario sourdough --verbose --step
```

Or use environment variables:

```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Structure Learning Concepts

### Hill-Climb vs K2

| Property | Hill-Climb | K2 |
|----------|-----------|-----|
| Search strategy | Greedy local search | Order-based forward search |
| Starting point | Empty graph | Empty graph + variable ordering |
| Operations | Add, remove, reverse edges | Add parent edges only |
| Ordering required | No | Yes (results depend on ordering) |
| Score function | BIC (default) | BDeu (default) |
| Complexity | O(n^2 * max_steps) | O(n^2 * max_parents) |
| Strengths | Flexible, no ordering needed | Fast, principled Bayesian scoring |
| Weaknesses | Can get stuck in local optima | Sensitive to variable ordering |

### Scoring Functions

**BIC (Bayesian Information Criterion)**: `BIC = LL - (k/2) * ln(N)` where LL is log-likelihood, k is the number of free parameters, and N is the sample size. Penalizes complexity more strongly with larger datasets.

**BDeu (Bayesian Dirichlet equivalent uniform)**: A Bayesian score that uses a Dirichlet prior. The equivalent sample size (ESS) parameter controls prior strength: small ESS values prefer simpler structures, large ESS values are more permissive.

### Parameter Learning (MLE)

Maximum Likelihood Estimation counts co-occurrences in the data to estimate conditional probability tables. Laplace smoothing (pseudocount > 0) adds a small count to every cell, preventing zero probabilities that would make log-likelihood undefined.

### Fit Evaluation (Log-Likelihood)

Log-likelihood measures how well the model's CPTs explain the observed data: `LL = sum_i sum_j log P(x_ij | parents(x_j))`. Higher (less negative) values indicate better fit. Per-sample log-likelihood (LL / N) normalizes for dataset size.

## CSV Format Requirements

- **Header row**: First row contains column names (become BN variable names)
- **Encoding**: UTF-8 with LF line endings
- **Delimiter**: Comma-separated values
- **Values**: Categorical (discrete) values only for structure learning
- **Missing values**: Rows with empty cells are skipped with a warning
- **Sorting**: Primary sort by first column, secondary by second column

### Adding a New Scenario

1. Create a new directory under `scenarios/`
2. Add a `data.csv` file with header row and at least 50 data rows
3. Ensure correlations in the data reflect the causal structure you expect to discover
4. Add the scenario configuration to `scenario_config()` (Rust) or `knownScenarios` (Go)
5. Create `expected-output.json` with expected edge ranges and inference results

## Real-World Applications

Structure learning from observational data is used in:

- **Epidemiology**: Discovering disease risk factor relationships from patient records
- **Manufacturing**: Identifying root causes of defects from production data
- **Finance**: Mapping causal relationships between economic indicators
- **Genomics**: Learning gene regulatory networks from expression data
- **Quality control**: Finding which process parameters affect product quality

The key insight is that structure learning automates the construction of causal models, which traditionally requires domain expert knowledge. By comparing multiple algorithms, practitioners can identify robust causal relationships with higher confidence.

## Testing

```bash
# Rust
cd rust && cargo test

# Go
cd go && go test -v
```

Each scenario includes an `expected-output.json` that describes expected edge count ranges, inference results, and fit evaluation bounds for regression testing.
