# LLM-Solver Hybrid -- Natural Language to Optimized Solutions

Demonstrates using an LLM to translate natural language constraints into structured solver variables and constraints, then feeding them to the Z3-based constraint solver for optimization. Supports mock mode (no API key needed) and live mode with configurable LLM providers.

> Bridge natural language and constraint solvers — let an LLM parse human intent, let Z3 find the optimal answer.

**Scenarios**: `seating` · `dungeon` · `road-trip`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Intermediate** 🟦 · LLM · Solver

- **Summary:** Hybrid LLM + Z3 solver problem solving
- **Scenario:** Use an LLM to formulate constraints and Z3 to solve them
- **`tech_tags` in manifest:** `LLM, Solver` — example id **`llm-solver-hybrid`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust, python (paths under this directory).
- **Models:** Set cloud provider API keys and/or run **Ollama** locally when you execute the **Run** steps (interactive flags like `--help` / `--verbose` are documented below).

## Key nxusKit Features Demonstrated

| Feature | Description | Rust | Go | Python |
|---------|-------------|------|-----|--------|
| **LLM Chat API** | Send structured prompts to LLM providers | `nxuskit::chat()` | `provider.Chat()` | `provider.chat(..., response_format=ResponseFormat.JSON)` |
| **Constraint Solver** | Z3-based solver session with variables, constraints, objectives | `nxuskit::solver::SolverSession` | `NewSolverSession()` | `nxuskit.solver.SolverSession` |
| **JSON Parsing/Validation** | Parse LLM output into typed variable and constraint definitions | `serde_json` | `encoding/json` | `json` + validation stage |
| **Retry Logic** | Re-prompt LLM on parse failure with error feedback (max 3 attempts) | `call_llm_with_retry()` | Retry loop in Stage 2 | Retry loop in `extract_variables_live()` |
| **Mock Mode** | Deterministic offline testing with pre-computed LLM responses | `--mock` flag | `--mock` (default) | `--mock` / `--no-mock` |
| **Provider Abstraction** | Same pipeline works with Ollama, LM Studio, OpenAI, Claude, Groq | `--provider` flag | `--provider` flag | `--provider` flag |

## Real-World Application

Natural language optimization, conversational planning.

## Technologies

LLM, Solver

## Architecture

```
┌──────────────┐     JSON      ┌───────────┐    Structured    ┌──────────┐
│ Natural Lang │ ──────────>  │    LLM    │ ──────────────>  │  Solver  │
│ Constraints  │   prompt     │  (or Mock) │   variables +   │   (Z3)   │
└──────────────┘              └───────────┘   constraints    └──────────┘
    problem.json                                                 │
                                                           Optimal Solution
```

**Stage 1 -- Load Problem**: Reads the scenario's `problem.json` containing natural language constraints, system prompt, objective definition, solver configuration, and a pre-computed mock LLM response.

**Stage 2 -- Get Structured Constraints**: In mock mode, uses the pre-defined `mock_llm_response` from `problem.json`. In live mode, sends the system prompt and natural language constraints to an LLM provider, parses the JSON response into variables and constraints arrays, and retries up to 3 times on parse failure.

**Stage 3 -- Validate**: Checks that each variable has a name, type, and domain. Verifies that all constraint variable references point to existing variable names. Filters out invalid constraints and reports warnings.

**Stage 4 -- Solve**: Creates a Z3 solver session, adds variables and constraints, sets the optimization objective, and solves. Falls back to satisfiability check if the objective cannot be applied.

**Stage 5 -- Interpret Results**: Renders solver assignments in scenario-specific human-readable format (table assignments, dungeon map, trip itinerary).

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/llm-solver-hybrid`:
cd rust && cargo build
cd go && make build
```

## Run

### Go

```bash
cd go
make build
./bin/llm-solver-hybrid --scenario seating
./bin/llm-solver-hybrid --scenario dungeon --verbose
./bin/llm-solver-hybrid --scenario road-trip --step
```

Or directly:

```bash
cd go
go run . --scenario seating
```

### Rust

```bash
cd rust
cargo run -- --scenario seating
cargo run -- --scenario dungeon --verbose
cargo run -- --scenario road-trip --step
```

### Python

```bash
cd python
python3 main.py --scenario seating
python3 main.py --scenario dungeon --verbose
python3 main.py --scenario road-trip --step
```

## Mock vs Live Mode

### Mock Mode (default)

Mock mode uses the pre-computed `mock_llm_response` from each scenario's `problem.json`. No API key or running LLM server is needed. This is the default for Rust, Go, and Python.

```bash
# Go (mock is the default)
go run . --scenario seating

# Rust (mock is the default)
cargo run -- --scenario seating

# Python (mock is the default)
python3 main.py --scenario seating
```

### Live Mode

Live mode calls a real LLM provider to extract structured constraints from natural language. The LLM response is parsed as JSON and validated before being sent to the solver.

```bash
# Go: disable mock with --no-mock
go run . --scenario seating --no-mock --provider ollama --model llama3.2

# Rust: disable mock with --no-mock
cargo run -- --scenario seating --no-mock --provider ollama --model llama3.2

# Python: disable mock with --no-mock
python3 main.py --scenario seating --no-mock --provider ollama --model llama3.2
```

**Supported providers**: `ollama`, `lmstudio`, `openai`, `claude`, `groq`

**API key setup** (for cloud providers):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GROQ_API_KEY=gsk_...
```

Local providers (Ollama, LM Studio) require the server to be running but no API key.

## Scenarios

### Seating -- Wedding Dinner Arrangement

Assign 12 wedding guests to 3 tables while respecting social constraints: feuding relatives at different tables, couples together, ex-partners separated, language requirements, and table capacity limits. The solver maximizes a happiness score based on social preferences.

- **Variables**: 12 integer variables (one per guest, domain 1--3)
- **Constraints**: 4 (not-equal, equal, linear capacity)
- **Objective**: maximize happiness

### Dungeon -- Game Level Layout

Generate a 5-room dungeon with boss placement, treasure rooms, and progressive difficulty. The boss must be in the last room, treasure rooms cannot overlap with the boss, and difficulty increases as the player goes deeper.

- **Variables**: 9 integer variables (room assignments, difficulty levels)
- **Constraints**: 5 (equality, not-equal, linear progression)
- **Objective**: maximize total challenge

### Road Trip -- National Park Itinerary

Plan a 14-day road trip visiting 5 national parks (Yosemite, Yellowstone, Zion, Glacier, Grand Canyon). Constraints include minimum days at large parks, geographic ordering (visit nearby parks consecutively), and the total day budget.

- **Variables**: 10 integer variables (days-at and visit-order per park)
- **Constraints**: 4 (linear budget, minimum days, ordering)
- **Objective**: maximize total experience

## Interactive Modes

All examples support debugging flags for inspecting pipeline internals:

```bash
# Verbose mode - show raw LLM responses, parsed JSON, solver details
cargo run -- --scenario seating --verbose       # Rust
go run . --scenario seating --verbose           # Go

# Step mode - pause at each pipeline stage with explanations
cargo run -- --scenario dungeon --step          # Rust
go run . --scenario dungeon --step              # Go

# Combined mode
cargo run -- --scenario road-trip --verbose --step
go run . --scenario road-trip --verbose --step
```

Or use environment variables:

```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Retry Logic

When running in live mode, the LLM extraction step uses a retry loop (max 3 attempts):

1. **Attempt 1**: Send the system prompt and natural language constraints to the LLM, requesting JSON output with `variables` and `constraints` arrays.
2. **Parse and validate**: Check that the response is valid JSON, contains non-empty `variables` and `constraints` arrays, and that variables have required fields.
3. **On failure**: Append the failed response and an error-feedback message to the conversation, then re-prompt the LLM. The feedback describes the specific parse error (invalid JSON, empty arrays, missing fields).
4. **After 3 failures**: Fall back to the mock response from `problem.json` and continue the pipeline.

This retry-with-feedback pattern is effective because the LLM sees its own previous attempt and the specific error, allowing it to self-correct.

## Scenario Data Format

Each scenario is defined by a single `problem.json` file in `scenarios/<name>/`:

| Field | Type | Purpose |
|-------|------|---------|
| `description` | string | Human-readable scenario description |
| `natural_language_constraints` | string[] | Plain English constraints sent to the LLM |
| `system_prompt` | string | System message instructing the LLM how to respond |
| `objective` | object | Optimization objective (`name`, `direction`, `expression`, `label`) |
| `solver_config` | object | Solver configuration (e.g., `timeout_ms`) |
| `mock_llm_response` | object | Pre-computed LLM output with `variables` and `constraints` arrays |

Each variable in `mock_llm_response.variables` has:

```json
{
    "name": "guest_anna_table",
    "var_type": "integer",
    "label": "Table assignment for Anna",
    "domain": { "min": 1, "max": 3 }
}
```

Each constraint in `mock_llm_response.constraints` has:

```json
{
    "name": "martha_bob_apart",
    "constraint_type": "not_equal",
    "label": "Aunt Martha and Uncle Bob at different tables",
    "variables": ["guest_martha_table", "guest_bob_table"],
    "parameters": {}
}
```

An `expected-output.json` file alongside each `problem.json` describes the expected pipeline results in mock mode, useful for regression testing.

### Adding a New Scenario

1. Create a new directory under `scenarios/`
2. Write a `problem.json` with natural language constraints and a mock LLM response
3. Add the scenario's result interpretation logic to `interpretResults` (Go) or `interpret_result` (Rust)
4. Create an `expected-output.json` with the expected mock-mode results

## Prompt Engineering Notes

The quality of LLM-extracted constraints depends heavily on the system prompt. Tips for writing effective prompts:

1. **Specify the output format explicitly**: Tell the LLM to return JSON with `variables` and `constraints` arrays. Mention the exact field names expected (`name`, `var_type`, `domain`, `constraint_type`, `parameters`).
2. **Define variable types and domains**: Instruct the LLM what variable types are available (`integer`, `boolean`) and how to express domains (`min`/`max` for integers).
3. **List supported constraint types**: Enumerate the solver's supported constraint types (`equal`, `not_equal`, `linear`) so the LLM does not invent unsupported types.
4. **Use concrete examples**: Include a short example variable and constraint in the system prompt to anchor the LLM's output format.
5. **Keep it focused**: One system prompt per domain. A seating-specific prompt outperforms a generic "convert any constraints" prompt.
6. **Request JSON-only output**: Explicitly state "Respond with JSON only" to prevent the LLM from wrapping the response in explanatory text or markdown code fences.

## Testing

```bash
# Rust
cd rust && cargo test

# Go
cd go && go test -v
```

Each scenario includes an `expected-output.json` that describes the expected structure of the pipeline results in mock mode, useful for regression testing and validation.
