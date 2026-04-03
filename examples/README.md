<!-- BEGIN: Auto-generated showcase (do not edit manually) -->

# nxusKit Examples

A curated collection of **32 production-ready examples** demonstrating LLM integration, rule engines, constraint solvers, Bayesian networks, and decision tables using the nxusKit SDK (nxuskit, nxuskit-go, nxuskit-py).

> **5 apps** | **17 patterns** | **10 integrations** — start with [Basic Chat](patterns/basic-chat/) or [Streaming](patterns/streaming/).

**Browse by:** [Scenario](#by-scenario) | [Real-World Application](#by-real-world-application) | [Technology](#by-technology) | [Language](#by-language) | [Acronym and Tag Key](#acronym-and-tag-key)

---

## Acronym and Tag Key

| Tag | Meaning |
|-----|---------|
| **LLM** | Large Language Model inference (chat, completion, streaming) |
| **CLIPS** | CLIPS (Rule-based Expert System Engine) |
| **Solver** | Z3 constraint solver |
| **BN** | Bayesian Network inference and learning |
| **ZEN** | ZEN decision table evaluation |
| **MCP** | Model Context Protocol |
| **Vision** | Vision and multimodal capabilities |
| **Streaming** | Server-Sent Events streaming responses |

---

## By Scenario

| Example | Tier | Category | Scenario | Real-World Application | Tags | Languages |
|---------|------|----------|----------|----------------------|------|-----------|
| [Basic Chat](patterns/basic-chat/) | Community | Pattern | Send a single chat message and receive a response | Customer support chatbot, FAQ assistant | LLM | rust, go, python |
| [Streaming](patterns/streaming/) | Community | Pattern | Stream tokens from a chat completion as they arrive | Real-time chat interface, live transcription display | LLM, Streaming | rust, go, python |
| [Multi Provider](patterns/multi-provider/) | Community | Pattern | Configure and switch between multiple LLM providers at runtime | Multi-vendor AI gateway, provider comparison tool | LLM | rust, go, python |
| [Convenience API](patterns/convenience-api/) | Community | Pattern | Use simplified one-liner API for quick LLM calls | Rapid prototyping, scripting with LLM capabilities | LLM | rust, go |
| [Blocking API](patterns/blocking-api/) | Community | Pattern | Make synchronous LLM calls without async runtime | CLI tools, batch processing scripts | LLM | rust, go |
| [Capability Detection](patterns/capability-detection/) | Community | Pattern | Query provider capabilities before dispatching requests | Adaptive AI middleware, feature-gated UX | LLM | rust, go |
| [Cost Routing](patterns/cost-routing/) | Community | Pattern | Route requests to cost-appropriate models based on task complexity | Cost-optimized inference, budget-aware model selection, prompt complexity tiering | LLM | rust, go, python |
| [Polymorphic](patterns/polymorphic/) | Community | Pattern | Use trait objects and interfaces to abstract over providers | Plugin architecture, provider-agnostic application layer | LLM | rust, go |
| [Retry Fallback](patterns/retry-fallback/) | Community | Pattern | Automatically retry failed requests and fall back to alternate providers | High-availability AI service, resilient inference pipeline | LLM | rust, go, python |
| [Structured Output](patterns/structured-output/) | Community | Pattern | Request and parse structured JSON responses from an LLM | Data extraction, form auto-fill, API response generation | LLM | rust, go, python |
| [Timeout Config](patterns/timeout-config/) | Community | Pattern | Configure request timeouts and connection pool settings | Latency-sensitive services, SLA-bound AI endpoints | LLM | rust, go, python |
| [Token Budget](patterns/token-budget/) | Community | Pattern | Track and limit token usage across requests | Usage metering, per-user quota enforcement | LLM | rust, go, python |
| [Vision](patterns/vision/) | Community | Pattern | Send images alongside text prompts for multimodal analysis | Image captioning, visual QA, document understanding | LLM, Vision | rust, go, python |
| [Auth Helper](patterns/auth-helper/) | Community | Pattern | List providers, check auth status, set credentials, initiate OAuth flows | Developer tooling, credential management, multi-provider auth setup | Auth, OAuth | rust, go |
| &nbsp;&nbsp;↳ `status` | | | List provider authentication status and stored credentials | | | |
| &nbsp;&nbsp;↳ `set` | | | Store an API key for a specific provider | | | |
| &nbsp;&nbsp;↳ `remove` | | | Remove a stored API key for a provider | | | |
| &nbsp;&nbsp;↳ `dashboard` | | | Open provider credential dashboard in browser | | | |
| [Solver](patterns/solver/) | Pro | Pattern | Define and solve constraint satisfaction problems with Z3 | Scheduling optimization, resource allocation, configuration validation | Solver | rust, go, python |
| &nbsp;&nbsp;↳ `theme-park` | | | Budget and space planning for a theme park with rides, food courts, and entertainment zones | | | |
| &nbsp;&nbsp;↳ `space-colony` | | | Resource allocation for a space colony dealing with solar storm what-if scenarios | | | |
| &nbsp;&nbsp;↳ `fantasy-draft` | | | Fantasy sports draft optimization under salary cap with injury what-if analysis | | | |
| [Bayesian Inference](patterns/bayesian-inference/) | Community | Pattern | Build a Bayesian network and perform probabilistic inference | Risk assessment, medical diagnosis support, fault detection | BN | rust, go, python |
| &nbsp;&nbsp;↳ `haunted-house` | | | Investigate a haunted house — is it a ghost or a raccoon? | | | |
| &nbsp;&nbsp;↳ `coffee-shop` | | | Diagnose bad espresso from grind size, temperature, and bean age | | | |
| &nbsp;&nbsp;↳ `plant-doctor` | | | Diagnose a sick plant from overwatering, nutrient, and disease evidence | | | |
| [Solver What If](patterns/solver-what-if/) | Pro | Pattern | Explore what-if scenarios with solver push/pop constraint scoping | Financial planning, capacity modeling, sensitivity analysis | Solver | rust, go, python |
| &nbsp;&nbsp;↳ `wedding` | | | Wedding budget planning with $25k constraint and vendor what-if scenarios | | | |
| &nbsp;&nbsp;↳ `mars` | | | Mars colony resource allocation with dust storm what-if disruptions | | | |
| &nbsp;&nbsp;↳ `recipe` | | | Recipe scaling with vegan substitution — may be UNSAT | | | |
| [Ollama](integrations/ollama/) | Community | Integration | Connect to a local Ollama instance for private LLM inference | On-premise AI deployment, air-gapped inference | LLM | rust, go, python |
| [LM Studio](integrations/lmstudio/) | Community | Integration | Connect to a local LM Studio server for desktop LLM inference | Developer local testing, offline prototyping | LLM | rust, go |
| [Alert Triage](integrations/alert-triage/) | Community | Integration | Classify and prioritize alerts using LLM reasoning | SOC alert triage, IT incident management | LLM | rust, go |
| [CLI Assistant](integrations/cli-assistant/) | Community | Integration | Build an interactive terminal assistant powered by an LLM | Developer productivity tool, command-line copilot | LLM | rust, go |
| [CLIPS Basics](integrations/clips-basics/) | Community | Integration | Load rules, assert facts, and run the CLIPS inference engine | Business rules engine, compliance checking | CLIPS | rust, go |
| [CLIPS LLM Hybrid](integrations/clips-llm-hybrid/) | Community | Integration | Combine deterministic CLIPS rules with LLM-based reasoning | Explainable AI decisions, regulated industry automation | LLM, CLIPS | rust, go, python |
| [BN Solver CLIPS Pipeline](integrations/bn-solver-clips-pipeline/) | Pro | Integration | Chain Bayesian Network prediction into Solver optimization with CLIPS safety enforcement | Multi-stage decision support, risk-aware optimization with safety validation | CLIPS, Solver, BN | rust, go |
| &nbsp;&nbsp;↳ `festival` | | | Music festival staging — crowd predictions drive band scheduling and safety | | | |
| &nbsp;&nbsp;↳ `rescue` | | | Search and rescue — survivor probability drives team assignment and safety checks | | | |
| &nbsp;&nbsp;↳ `bakery` | | | Bakery scheduling — demand forecasts drive oven allocation and allergen separation | | | |
| [LLM Solver Hybrid](integrations/llm-solver-hybrid/) | Pro | Integration | Use an LLM to formulate constraints and Z3 to solve them | Natural language optimization, conversational planning | LLM, Solver | rust, go, python |
| &nbsp;&nbsp;↳ `seating` | | | Wedding dinner seating — 12 guests across 3 tables with constraints | | | |
| &nbsp;&nbsp;↳ `dungeon` | | | Dungeon layout — 5 rooms with boss and treasure placement rules | | | |
| &nbsp;&nbsp;↳ `road-trip` | | | Road trip planning — 14 days across 5 national parks with preferences | | | |
| [BN Structure Learning](integrations/bn-structure-learning/) | Community | Integration | Learn Bayesian network structure from observational data | Causal discovery, epidemiological modeling, root cause analysis | BN | rust, go, python |
| &nbsp;&nbsp;↳ `golf` | | | Golf course conditions — weather, soil, and maintenance factor learning | | | |
| &nbsp;&nbsp;↳ `bmx` | | | BMX performance — skill level, technique, and jump factor learning | | | |
| &nbsp;&nbsp;↳ `sourdough` | | | Sourdough baking — feeding schedule, flour type, and temperature factor learning | | | |
| [ZEN Decisions](integrations/zen-decisions/) | Pro | Integration | Evaluate business decision tables using the ZEN engine | Pricing rules, eligibility determination, policy evaluation | ZEN | rust, go, python |
| &nbsp;&nbsp;↳ `maze-rat` | | | First Hit Policy — route a maze runner through personality-driven decisions | | | |
| &nbsp;&nbsp;↳ `potion` | | | Collect Hit Policy — match ingredient lists against brewing recipes | | | |
| &nbsp;&nbsp;↳ `food-truck` | | | Expression Nodes — compute dynamic pricing with conditional logic | | | |
| [Puzzler](apps/puzzler/) | Pro | App | Compare CLIPS rule-based, LLM reasoning, and hybrid approaches for solving logic puzzles | AI strategy comparison, constraint vs neural solving benchmarks, educational puzzle platforms | LLM, CLIPS, Solver | rust, go |
| &nbsp;&nbsp;↳ `sudoku` | | | Solve Sudoku puzzles using CLIPS constraint propagation | | | |
| &nbsp;&nbsp;↳ `set-game` | | | Find valid SET card combinations using CLIPS pattern matching | | | |
| &nbsp;&nbsp;↳ `compare` | | | Side-by-side comparison of CLIPS, LLM, and hybrid solvers | | | |
| [Racer](apps/racer/) | Pro | App | Race CLIPS rule-based solving against LLM reasoning on logic puzzles | AI approach comparison, rule engine vs LLM benchmarking, hybrid strategy selection | LLM, CLIPS | rust, go |
| &nbsp;&nbsp;↳ `race` | | | Head-to-head CLIPS vs LLM race on a single problem | | | |
| &nbsp;&nbsp;↳ `benchmark` | | | Statistical benchmarking with multiple runs and timing | | | |
| &nbsp;&nbsp;↳ `list` | | | List all available problems with difficulty ratings | | | |
| &nbsp;&nbsp;↳ `describe` | | | Show detailed description of a specific problem | | | |
| [Riffer](apps/riffer/) | Pro | App | Analyze, score, and transform music sequences with optional CLIPS and LLM enhancements | Music theory analysis, algorithmic composition assistance, MIDI/MusicXML processing | LLM, CLIPS | rust, go |
| &nbsp;&nbsp;↳ `analyze` | | | Analyze a music sequence for key, intervals, and rhythm patterns | | | |
| &nbsp;&nbsp;↳ `score` | | | Score a sequence on six musical dimensions | | | |
| &nbsp;&nbsp;↳ `transform` | | | Transform a sequence — transpose, invert, or retrograde | | | |
| &nbsp;&nbsp;↳ `convert` | | | Convert between MIDI and MusicXML formats | | | |
| [Ruler](apps/ruler/) | Pro | App | Describe business rules in natural language and generate validated CLIPS code using LLM | Low-code rule authoring, natural language business logic, automated CLIPS code generation | LLM, CLIPS | rust, go |
| &nbsp;&nbsp;↳ `generate` | | | Generate CLIPS rules from natural language descriptions | | | |
| &nbsp;&nbsp;↳ `validate` | | | Validate CLIPS rule syntax and semantic correctness | | | |
| &nbsp;&nbsp;↳ `save` | | | Save generated rules to a file for later use | | | |
| &nbsp;&nbsp;↳ `load` | | | Load previously saved rules from a file | | | |
| &nbsp;&nbsp;↳ `examples` | | | Run progressive complexity examples demonstrating rule generation | | | |
| [Arbiter](apps/arbiter/) | Pro | App | Submit questions to an LLM and validate answers against CLIPS rules, retrying on validation failure | Reliable AI answers with deterministic validation, LLM output verification, hybrid rule+LLM pipelines | LLM, CLIPS | rust, go |
| &nbsp;&nbsp;↳ `classification` | | | Categorize input text into specified categories | | | |
| &nbsp;&nbsp;↳ `extraction` | | | Extract structured information from unstructured text | | | |
| &nbsp;&nbsp;↳ `reasoning` | | | Perform logical inference and multi-step reasoning | | | |

---

## By Real-World Application

### AI approach comparison, rule engine vs LLM benchmarking, hybrid strategy selection
- [racer](apps/racer/)

### AI strategy comparison, constraint vs neural solving benchmarks, educational puzzle platforms
- [puzzler](apps/puzzler/)

### Adaptive AI middleware, feature-gated UX
- [capability-detection](patterns/capability-detection/)

### Business rules engine, compliance checking
- [clips-basics](integrations/clips-basics/)

### CLI tools, batch processing scripts
- [blocking-api](patterns/blocking-api/)

### Causal discovery, epidemiological modeling, root cause analysis
- [bn-structure-learning](integrations/bn-structure-learning/)

### Cost-optimized inference, budget-aware model selection, prompt complexity tiering
- [cost-routing](patterns/cost-routing/)

### Customer support chatbot, FAQ assistant
- [basic-chat](patterns/basic-chat/)

### Data extraction, form auto-fill, API response generation
- [structured-output](patterns/structured-output/)

### Developer local testing, offline prototyping
- [lmstudio](integrations/lmstudio/)

### Developer productivity tool, command-line copilot
- [cli-assistant](integrations/cli-assistant/)

### Developer tooling, credential management, multi-provider auth setup
- [auth-helper](patterns/auth-helper/)

### Explainable AI decisions, regulated industry automation
- [clips-llm-hybrid](integrations/clips-llm-hybrid/)

### Financial planning, capacity modeling, sensitivity analysis
- [solver-what-if](patterns/solver-what-if/)

### High-availability AI service, resilient inference pipeline
- [retry-fallback](patterns/retry-fallback/)

### Image captioning, visual QA, document understanding
- [vision](patterns/vision/)

### Latency-sensitive services, SLA-bound AI endpoints
- [timeout-config](patterns/timeout-config/)

### Low-code rule authoring, natural language business logic, automated CLIPS code generation
- [ruler](apps/ruler/)

### Multi-stage decision support, risk-aware optimization with safety validation
- [bn-solver-clips-pipeline](integrations/bn-solver-clips-pipeline/)

### Multi-vendor AI gateway, provider comparison tool
- [multi-provider](patterns/multi-provider/)

### Music theory analysis, algorithmic composition assistance, MIDI/MusicXML processing
- [riffer](apps/riffer/)

### Natural language optimization, conversational planning
- [llm-solver-hybrid](integrations/llm-solver-hybrid/)

### On-premise AI deployment, air-gapped inference
- [ollama](integrations/ollama/)

### Plugin architecture, provider-agnostic application layer
- [polymorphic](patterns/polymorphic/)

### Pricing rules, eligibility determination, policy evaluation
- [zen-decisions](integrations/zen-decisions/)

### Rapid prototyping, scripting with LLM capabilities
- [convenience-api](patterns/convenience-api/)

### Real-time chat interface, live transcription display
- [streaming](patterns/streaming/)

### Reliable AI answers with deterministic validation, LLM output verification, hybrid rule+LLM pipelines
- [arbiter](apps/arbiter/)

### Risk assessment, medical diagnosis support, fault detection
- [bayesian-inference](patterns/bayesian-inference/)

### SOC alert triage, IT incident management
- [alert-triage](integrations/alert-triage/)

### Scheduling optimization, resource allocation, configuration validation
- [solver](patterns/solver/)

### Usage metering, per-user quota enforcement
- [token-budget](patterns/token-budget/)

---

## By Technology

### LLM

- [Basic Chat](patterns/basic-chat/)
- [Streaming](patterns/streaming/)
- [Multi Provider](patterns/multi-provider/)
- [Convenience API](patterns/convenience-api/)
- [Blocking API](patterns/blocking-api/)
- [Capability Detection](patterns/capability-detection/)
- [Cost Routing](patterns/cost-routing/)
- [Polymorphic](patterns/polymorphic/)
- [Retry Fallback](patterns/retry-fallback/)
- [Structured Output](patterns/structured-output/)
- [Timeout Config](patterns/timeout-config/)
- [Token Budget](patterns/token-budget/)
- [Vision](patterns/vision/)
- [Ollama](integrations/ollama/)
- [LM Studio](integrations/lmstudio/)
- [Alert Triage](integrations/alert-triage/)
- [CLI Assistant](integrations/cli-assistant/)
- [CLIPS LLM Hybrid](integrations/clips-llm-hybrid/)
- [LLM Solver Hybrid](integrations/llm-solver-hybrid/)
- [Puzzler](apps/puzzler/)
- [Racer](apps/racer/)
- [Riffer](apps/riffer/)
- [Ruler](apps/ruler/)
- [Arbiter](apps/arbiter/)

### CLIPS

- [CLIPS Basics](integrations/clips-basics/)
- [CLIPS LLM Hybrid](integrations/clips-llm-hybrid/)
- [BN Solver CLIPS Pipeline](integrations/bn-solver-clips-pipeline/)
- [Puzzler](apps/puzzler/)
- [Racer](apps/racer/)
- [Riffer](apps/riffer/)
- [Ruler](apps/ruler/)
- [Arbiter](apps/arbiter/)

### Solver

- [Solver](patterns/solver/)
- [Solver What If](patterns/solver-what-if/)
- [BN Solver CLIPS Pipeline](integrations/bn-solver-clips-pipeline/)
- [LLM Solver Hybrid](integrations/llm-solver-hybrid/)
- [Puzzler](apps/puzzler/)

### BN

- [Bayesian Inference](patterns/bayesian-inference/)
- [BN Solver CLIPS Pipeline](integrations/bn-solver-clips-pipeline/)
- [BN Structure Learning](integrations/bn-structure-learning/)

### ZEN

- [ZEN Decisions](integrations/zen-decisions/)

### Vision

- [Vision](patterns/vision/)

### Streaming

- [Streaming](patterns/streaming/)

---

## By Language

| Example | Category | Rust | Go | Python |
|---------|----------|------|-----|--------|
| [Basic Chat](patterns/basic-chat/) | patterns | Yes | Yes | Yes |
| [Streaming](patterns/streaming/) | patterns | Yes | Yes | Yes |
| [Multi Provider](patterns/multi-provider/) | patterns | Yes | Yes | Yes |
| [Convenience API](patterns/convenience-api/) | patterns | Yes | Yes | - |
| [Blocking API](patterns/blocking-api/) | patterns | Yes | Yes | - |
| [Capability Detection](patterns/capability-detection/) | patterns | Yes | Yes | - |
| [Cost Routing](patterns/cost-routing/) | patterns | Yes | Yes | Yes |
| [Polymorphic](patterns/polymorphic/) | patterns | Yes | Yes | - |
| [Retry Fallback](patterns/retry-fallback/) | patterns | Yes | Yes | Yes |
| [Structured Output](patterns/structured-output/) | patterns | Yes | Yes | Yes |
| [Timeout Config](patterns/timeout-config/) | patterns | Yes | Yes | Yes |
| [Token Budget](patterns/token-budget/) | patterns | Yes | Yes | Yes |
| [Vision](patterns/vision/) | patterns | Yes | Yes | Yes |
| [Auth Helper](patterns/auth-helper/) | patterns | Yes | Yes | - |
| [Solver](patterns/solver/) | patterns | Yes | Yes | Yes |
| [Bayesian Inference](patterns/bayesian-inference/) | patterns | Yes | Yes | Yes |
| [Solver What If](patterns/solver-what-if/) | patterns | Yes | Yes | Yes |
| [Ollama](integrations/ollama/) | integrations | Yes | Yes | Yes |
| [LM Studio](integrations/lmstudio/) | integrations | Yes | Yes | - |
| [Alert Triage](integrations/alert-triage/) | integrations | Yes | Yes | - |
| [CLI Assistant](integrations/cli-assistant/) | integrations | Yes | Yes | - |
| [CLIPS Basics](integrations/clips-basics/) | integrations | Yes | Yes | - |
| [CLIPS LLM Hybrid](integrations/clips-llm-hybrid/) | integrations | Yes | Yes | Yes |
| [BN Solver CLIPS Pipeline](integrations/bn-solver-clips-pipeline/) | integrations | Yes | Yes | - |
| [LLM Solver Hybrid](integrations/llm-solver-hybrid/) | integrations | Yes | Yes | Yes |
| [BN Structure Learning](integrations/bn-structure-learning/) | integrations | Yes | Yes | Yes |
| [ZEN Decisions](integrations/zen-decisions/) | integrations | Yes | Yes | Yes |
| [Puzzler](apps/puzzler/) | apps | Yes | Yes | - |
| [Racer](apps/racer/) | apps | Yes | Yes | - |
| [Riffer](apps/riffer/) | apps | Yes | Yes | - |
| [Ruler](apps/ruler/) | apps | Yes | Yes | - |
| [Arbiter](apps/arbiter/) | apps | Yes | Yes | - |


<!-- END: Auto-generated showcase -->

## Quick Start

Each example includes Rust and Go implementations (some also include Python). Pick any example and run:

```bash
# Rust
cd examples/patterns/basic-chat/rust
cargo run

# Go
cd examples/patterns/basic-chat/go
make build && bin/basic-chat

# Python (where available)
cd examples/patterns/basic-chat/python
python main.py
```

## Interactive Modes

All examples support two debugging modes to help you understand what's happening:

### Verbose Mode (`--verbose` or `-v`)

Shows raw HTTP request/response data, useful for debugging API interactions:

```bash
# Rust
cargo run -- --verbose

# Go
go run . --verbose

# Python
python main.py --verbose
```

Output includes:
- Full JSON request bodies (with base64 data summarized)
- HTTP status codes and response times
- Streaming chunk data for SSE responses

### Step Mode (`--step` or `-s`)

Pauses at each major step with educational explanations:

```bash
# Rust
cargo run -- --step

# Go
go run . --step

# Python
python main.py --step
```

Controls:
- **Enter**: Continue to next step
- **q**: Quit the example
- **s**: Skip remaining steps and run to completion

### Environment Variables

As an alternative to CLI flags:

```bash
export NXUSKIT_VERBOSE=1        # Enable verbose mode
export NXUSKIT_STEP=1           # Enable step mode
export NXUSKIT_VERBOSE_LIMIT=5000  # Max chars before truncation
```

### Combined Mode

Use both flags together for maximum insight:

```bash
cargo run -- --verbose --step
```

## Prerequisites

- **nxusKit SDK** installed at `~/.nxuskit/sdk/current/` (see [top-level README](../README.md))
- **Rust examples**: Rust 1.93+ with Cargo, plus `./scripts/setup-sdk-symlink.sh` (run once)
- **Go examples**: Go 1.24+, plus `source ~/.nxuskit/sdk/current/scripts/setup-sdk.sh` (run once)
- **Python examples**: Python 3.11+
- **Local LLM**: Ollama running on localhost:11434 (or set `OLLAMA_HOST`)

## Directory Structure

```
examples/
├── apps/                    # Full application examples
│   └── <app-name>/
│       ├── README.md        # Documentation
│       ├── rust/            # Rust implementation
│       ├── go/              # Go implementation
│       └── shared/          # Shared data, config, rules
│
├── patterns/                # Design pattern examples
│   └── <pattern-name>/
│       ├── README.md        # Documentation
│       ├── rust/
│       └── go/
│
├── integrations/            # Integration examples
│   └── <integration-name>/
│       ├── README.md
│       ├── rust/
│       └── go/
│
├── shared/                  # Shared across all examples
│   ├── data/               # Common test data
│   ├── rules/              # CLIPS rule files
│   ├── prompts/            # Prompt templates
│   └── rust-support/       # Rust support crate (llm-patterns)
│
└── debug/                   # Debug/test utilities
```

## Running Tests

All examples include unit tests:

```bash
# Run Rust tests for a specific example
cd examples/patterns/basic-chat/rust
cargo test

# Run Go tests for a specific example
cd examples/patterns/basic-chat/go
go test -v ./...
```

## Local Development

### Rust

Rust examples depend on the nxusKit SDK installed at `~/.nxuskit/sdk/current/rust/`.
Run the setup script once after cloning to generate the Cargo paths override:

```bash
./scripts/setup-sdk-symlink.sh
```

This generates `.cargo/config.toml` (git-ignored) which tells Cargo to resolve the
`nxuskit` crate from your installed SDK. Without this step, builds fail with a clear
error message pointing to the setup script.

```bash
# Build from example directory
cd examples/patterns/basic-chat/rust
cargo build
```

### Go

A `go.work` file at the repository root enables local development. Go binaries
are always built to a `bin/` subdirectory:

```bash
# Using Makefile (preferred)
cd examples/patterns/basic-chat/go
make build    # Builds to bin/basic-chat
make test     # Runs tests
make clean    # Removes bin/

# Or build all examples at once
./scripts/build-go-examples.sh
```

## Environment Configuration

Create a `.env` file in any example directory:

```bash
# Optional: Custom Ollama host
OLLAMA_HOST=http://localhost:11434

# For examples using cloud providers
# OPENAI_API_KEY=...
# ANTHROPIC_API_KEY=...
```

## Contributing

When adding new examples:

1. Follow the directory structure above
2. Include Rust and Go implementations (Python where applicable)
3. Add an entry to `conformance/examples_manifest.json` with all required fields
4. Add unit tests using mock providers
5. Create a README.md with scenario, real-world application, tech tags, and run instructions
6. Run `bash scripts/generate-examples-showcase.sh --generate` to update the showcase
7. Keep examples focused on one pattern/integration
