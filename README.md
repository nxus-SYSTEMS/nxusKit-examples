# nxusKit Examples

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](LICENSE)
![Rust](https://img.shields.io/badge/Rust-000000?logo=rust&logoColor=white)
![Go](https://img.shields.io/badge/Go-00ADD8?logo=go&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)

**[Examples Docs](https://docs.nxus.systems/nxuskit/examples/)** · **[SDK Docs](https://docs.nxus.systems/nxuskit/)** · **[nxusKit SDK](https://github.com/nxus-SYSTEMS/nxusKit)** · **[Examples Portfolio](https://nxus.systems/examples)** · **[Website](https://nxus.systems)**

34 production-quality examples for the nxusKit SDK in Rust, Go, and Python, plus selected CLI/Bash implementations for shell-first orchestration — covering LLM patterns, CLIPS rule engines, Z3 constraint solvers, Bayesian networks, and ZEN decision tables.

## A Word About CLIPS

During its development at NASA from 1985 to 1996, the primary CLIPS
contributors were: Robert Savely, who conceived and championed the project;
Chris Culbert, who managed the project; Gary Riley and Brian Dantes, who were
the lead developers; and Frank Lopez, who developed the first version. Since
leaving NASA in 1996, Gary Riley has maintained CLIPS as public domain
software.

## Quick Start

```bash
# 1. Install the SDK (see https://docs.nxus.systems/nxuskit/getting-started/installation/)
# 2. Set up this project
source ~/.nxuskit/sdk/current/scripts/setup-sdk.sh   # Go, env vars, library paths
./scripts/setup-sdk-symlink.sh                        # Rust Cargo paths override

# 3. Run an example
cargo run --manifest-path examples/patterns/basic-chat/rust/Cargo.toml    # Rust
go run -tags nxuskit ./examples/patterns/basic-chat/go                    # Go
python examples/patterns/basic-chat/python/main.py                        # Python
```

## Examples

<!-- EXAMPLES-TABLE:START -->

### Patterns — Reusable SDK integration patterns

| Example | Description | Languages |
|---------|-------------|-----------|
| [basic-chat](examples/patterns/basic-chat/) | Basic chat completion with a simple prompt | Rust, Go, Python |
| [streaming](examples/patterns/streaming/) | Streaming chat completion with real-time output | Rust, Go, Python |
| [multi-provider](examples/patterns/multi-provider/) | Using multiple providers in one application | Rust, Go, Python, CLI/Bash |
| [convenience-api](examples/patterns/convenience-api/) | LiteLLM-style convenience API usage | Rust, Go |
| [blocking-api](examples/patterns/blocking-api/) | Synchronous blocking API for simpler use cases | Rust, Go |
| [capability-detection](examples/patterns/capability-detection/) | Detecting provider capabilities at runtime | Rust, Go, CLI/Bash |
| [cost-routing](examples/patterns/cost-routing/) | Cost-aware provider routing and selection | Rust, Go, Python, CLI/Bash |
| [polymorphic](examples/patterns/polymorphic/) | Polymorphic provider patterns with trait objects | Rust, Go |
| [retry-fallback](examples/patterns/retry-fallback/) | Retry and fallback strategies across providers | Rust, Go, Python, CLI/Bash |
| [structured-output](examples/patterns/structured-output/) | JSON mode and structured output generation | Rust, Go, Python, CLI/Bash |
| [timeout-config](examples/patterns/timeout-config/) | Timeout configuration and connection management | Rust, Go, Python |
| [token-budget](examples/patterns/token-budget/) | Token budget management and cost estimation | Rust, Go, Python, CLI/Bash |
| [vision](examples/patterns/vision/) | Vision and multimodal capabilities with images | Rust, Go, Python, CLI/Bash |
| [auth-helper](examples/patterns/auth-helper/) | OAuth login flow and credential management helper | Rust, Go |
| &nbsp;&nbsp;↳ `status` | List provider authentication status and stored credentials | |
| &nbsp;&nbsp;↳ `set` | Store an API key for a specific provider | |
| &nbsp;&nbsp;↳ `remove` | Remove a stored API key for a provider | |
| &nbsp;&nbsp;↳ `dashboard` | Open provider credential dashboard in browser | |
| [solver](examples/patterns/solver/) | Z3 constraint solver integration via nxusKit SDK | Rust, Go, Python, CLI/Bash |
| &nbsp;&nbsp;↳ `theme-park` | Budget and space planning for a theme park with rides, food courts, and entertainment zones | |
| &nbsp;&nbsp;↳ `space-colony` | Resource allocation for a space colony dealing with solar storm what-if scenarios | |
| &nbsp;&nbsp;↳ `fantasy-draft` | Fantasy sports draft optimization under salary cap with injury what-if analysis | |
| &nbsp;&nbsp;↳ real-world: **Theme Park Planning** | Facility layout, capital budgeting, resource allocation | |
| &nbsp;&nbsp;↳ real-world: **Space Colony Planning** | Infrastructure sizing, capacity planning, disaster recovery modeling | |
| &nbsp;&nbsp;↳ real-world: **Fantasy Sports Draft** | Portfolio optimization, team composition, auction bidding strategies | |
| [bayesian-inference](examples/patterns/bayesian-inference/) | Bayesian network inference via nxusKit SDK | Rust, Go, Python, CLI/Bash |
| &nbsp;&nbsp;↳ `haunted-house` | Investigate a haunted house — is it a ghost or a raccoon? | |
| &nbsp;&nbsp;↳ `coffee-shop` | Diagnose bad espresso from grind size, temperature, and bean age | |
| &nbsp;&nbsp;↳ `plant-doctor` | Diagnose a sick plant from overwatering, nutrient, and disease evidence | |
| &nbsp;&nbsp;↳ real-world: **Haunted House** | Fault diagnosis, anomaly detection, sensor fusion from multiple noisy sensors pointing to hidden causes | |
| &nbsp;&nbsp;↳ real-world: **Coffee Shop** | Manufacturing quality control, process parameter tuning, root cause analysis in production | |
| &nbsp;&nbsp;↳ real-world: **Plant Doctor** | Medical diagnosis, agricultural advisory systems, multi-symptom differential diagnosis | |
| [solver-what-if](examples/patterns/solver-what-if/) | What-if scenario analysis with solver scoping | Rust, Go, Python, CLI/Bash |
| &nbsp;&nbsp;↳ `wedding` | Wedding budget planning with $25k constraint and vendor what-if scenarios | |
| &nbsp;&nbsp;↳ `mars` | Mars colony resource allocation with dust storm what-if disruptions | |
| &nbsp;&nbsp;↳ `recipe` | Recipe scaling with vegan substitution — may be UNSAT | |
| &nbsp;&nbsp;↳ real-world: **Wedding Budget Planning** | Event planning, capital budgeting, portfolio allocation | |
| &nbsp;&nbsp;↳ real-world: **Mars Colony Planning** | Infrastructure sizing, supply chain planning, disaster preparedness | |
| &nbsp;&nbsp;↳ real-world: **Recipe Scaling** | Manufacturing scaling, formulation optimization, process engineering | |

### Integrations — Combining SDK features

| Example | Description | Languages |
|---------|-------------|-----------|
| [ollama](examples/integrations/ollama/) | Using Ollama for local inference | Rust, Go, Python |
| [lmstudio](examples/integrations/lmstudio/) | Using LM Studio for local inference | Rust, Go |
| [alert-triage](examples/integrations/alert-triage/) | Alert triage with LLM-powered analysis | Rust, Go, CLI/Bash |
| [cli-assistant](examples/integrations/cli-assistant/) | Interactive CLI assistant with LLM backend | Rust, Go |
| [clips-basics](examples/integrations/clips-basics/) | CLIPS rule engine basics via nxusKit SDK | Rust, Go, CLI/Bash |
| [clips-llm-hybrid](examples/integrations/clips-llm-hybrid/) | Hybrid CLIPS rules + LLM reasoning | Rust, Go, Python, CLI/Bash |
| [common-sense-guardrails](examples/integrations/common-sense-guardrails/) | Progressive LLM guardrails with CE CLIPS/BN and optional Pro Solver/ZEN repair feedback | Python, CLI/Bash |
| &nbsp;&nbsp;↳ `car-wash` | Catch the classic car-wash walk-vs-drive failure with CLIPS rules and optional Solver/Z3 feasibility | |
| &nbsp;&nbsp;↳ `coupon-stack` | Reject promotion stacking that violates eligibility and margin policy, with optional ZEN validation and BN risk scoring | |
| &nbsp;&nbsp;↳ `pallet-door` | Block unsafe warehouse advice that ignores dimensional clearance, with optional Solver/Z3 feasibility | |
| &nbsp;&nbsp;↳ `cold-chain` | Prevent cheaper logistics recommendations that violate handling requirements, with optional ZEN validation and BN review-risk scoring | |
| &nbsp;&nbsp;↳ `synthetic-claims-audit` | Inspect synthetic administrative data-quality and evidence-completeness findings as a review record | |
| &nbsp;&nbsp;↳ real-world: **LLM answer validation** | Catch plausible recommendations that fail physical, operational, or policy preconditions before they reach users | |
| &nbsp;&nbsp;↳ real-world: **Policy enforcement** | Turn free-form answers into facts, apply deterministic rules, and produce auditable repair context | |
| &nbsp;&nbsp;↳ real-world: **Operational decision support** | Preserve fast LLM drafting while requiring concrete feasibility evidence for workflow-critical recommendations | |
| [model-research-harness](examples/integrations/model-research-harness/) | Python-first harness for provider-neutral model research, Promptfoo import, CLIPS policy, Bayesian scoring, and dry-run lifecycle recommendations | Python, CLI/Bash |
| &nbsp;&nbsp;↳ `basic-ticket-routing` | Run a credentials-free support ticket classification research smoke | |
| &nbsp;&nbsp;↳ `promptfoo-import` | Import a Promptfoo config and run the converted nxusKit harness matrix | |
| &nbsp;&nbsp;↳ `software-dev` | Evaluate code analysis, bug finding, patching, generation, refactoring, and review outputs | |
| &nbsp;&nbsp;↳ real-world: **Model evaluation** | Score model candidates against task-specific outputs and report confidence instead of relying on ad hoc impressions | |
| &nbsp;&nbsp;↳ real-world: **Provider comparison** | Compare local and cloud providers through one provider-neutral workflow while keeping capability claims honest | |
| &nbsp;&nbsp;↳ real-world: **Lifecycle policy** | Generate dry-run pull, pin, keep, or retest recommendations bounded by deterministic policy | |
| &nbsp;&nbsp;↳ real-world: **Software development workflow research** | Exercise code analysis, bug finding, bugfixing, generation, refactoring, and review scenarios with public-safe fixtures | |
| [bn-solver-clips-pipeline](examples/integrations/bn-solver-clips-pipeline/) | Three-stage BN prediction → Solver optimization → CLIPS safety pipeline | Rust, Go, CLI/Bash |
| &nbsp;&nbsp;↳ `festival` | Music festival staging — crowd predictions drive band scheduling and safety | |
| &nbsp;&nbsp;↳ `rescue` | Search and rescue — survivor probability drives team assignment and safety checks | |
| &nbsp;&nbsp;↳ `bakery` | Bakery scheduling — demand forecasts drive oven allocation and allergen separation | |
| &nbsp;&nbsp;↳ real-world: **Event planning** | Predict attendance, optimize resource allocation, enforce safety codes | |
| &nbsp;&nbsp;↳ real-world: **Emergency response** | Estimate survival windows, deploy rescue assets, enforce operational protocols | |
| &nbsp;&nbsp;↳ real-world: **Manufacturing** | Forecast demand, schedule production, enforce quality and safety standards | |
| &nbsp;&nbsp;↳ real-world: **Logistics** | Predict delivery volumes, optimize fleet routing, enforce regulatory compliance | |
| &nbsp;&nbsp;↳ real-world: **Healthcare** | Predict patient load, optimize staff scheduling, enforce clinical safety protocols | |
| [llm-solver-hybrid](examples/integrations/llm-solver-hybrid/) | Hybrid LLM + Z3 solver problem solving | Rust, Go, Python, CLI/Bash |
| &nbsp;&nbsp;↳ `seating` | Wedding dinner seating — 12 guests across 3 tables with constraints | |
| &nbsp;&nbsp;↳ `dungeon` | Dungeon layout — 5 rooms with boss and treasure placement rules | |
| &nbsp;&nbsp;↳ `road-trip` | Road trip planning — 14 days across 5 national parks with preferences | |
| [bn-structure-learning](examples/integrations/bn-structure-learning/) | Bayesian network structure learning from data | Rust, Go, Python |
| &nbsp;&nbsp;↳ `golf` | Golf course conditions — weather, soil, and maintenance factor learning | |
| &nbsp;&nbsp;↳ `bmx` | BMX performance — skill level, technique, and jump factor learning | |
| &nbsp;&nbsp;↳ `sourdough` | Sourdough baking — feeding schedule, flour type, and temperature factor learning | |
| &nbsp;&nbsp;↳ real-world: **Epidemiology** | Discover disease risk factor relationships from patient records | |
| &nbsp;&nbsp;↳ real-world: **Manufacturing** | Identify root causes of defects from production data | |
| &nbsp;&nbsp;↳ real-world: **Finance** | Map causal relationships between economic indicators | |
| &nbsp;&nbsp;↳ real-world: **Genomics** | Learn gene regulatory networks from expression data | |
| &nbsp;&nbsp;↳ real-world: **Quality control** | Find which process parameters affect product quality | |
| [zen-decisions](examples/integrations/zen-decisions/) | ZEN decision table evaluation via nxusKit SDK | Rust, Go, Python, CLI/Bash |
| &nbsp;&nbsp;↳ `maze-rat` | First Hit Policy — route a maze runner through personality-driven decisions | |
| &nbsp;&nbsp;↳ `potion` | Collect Hit Policy — match ingredient lists against brewing recipes | |
| &nbsp;&nbsp;↳ `food-truck` | Expression Nodes — compute dynamic pricing with conditional logic | |

### Apps — Complete applications

| Example | Description | Languages |
|---------|-------------|-----------|
| [puzzler](examples/apps/puzzler/) | Multi-approach puzzle solver comparing CLIPS, LLM, and hybrid strategies | Rust, Go |
| &nbsp;&nbsp;↳ `sudoku` | Solve Sudoku puzzles using CLIPS constraint propagation | |
| &nbsp;&nbsp;↳ `set-game` | Find valid SET card combinations using CLIPS pattern matching | |
| &nbsp;&nbsp;↳ `compare` | Side-by-side comparison of CLIPS, LLM, and hybrid solvers | |
| [racer](examples/apps/racer/) | CLIPS vs LLM head-to-head benchmarking tool | Rust, Go |
| &nbsp;&nbsp;↳ `race` | Head-to-head CLIPS vs LLM race on a single problem | |
| &nbsp;&nbsp;↳ `benchmark` | Statistical benchmarking with multiple runs and timing | |
| &nbsp;&nbsp;↳ `list` | List all available problems with difficulty ratings | |
| &nbsp;&nbsp;↳ `describe` | Show detailed description of a specific problem | |
| [riffer](examples/apps/riffer/) | Music sequence analysis and transformation tool (still learning to shred) | Rust, Go |
| &nbsp;&nbsp;↳ `analyze` | Analyze a music sequence for key, intervals, and rhythm patterns | |
| &nbsp;&nbsp;↳ `score` | Score a sequence on six musical dimensions | |
| &nbsp;&nbsp;↳ `transform` | Transform a sequence — transpose, invert, or retrograde | |
| &nbsp;&nbsp;↳ `convert` | Convert between MIDI and MusicXML formats | |
| [ruler](examples/apps/ruler/) | LLM-powered CLIPS rule generator with automatic validation | Rust, Go, CLI/Bash |
| &nbsp;&nbsp;↳ `generate` | Generate CLIPS rules from natural language descriptions | |
| &nbsp;&nbsp;↳ `validate` | Validate CLIPS rule syntax and semantic correctness | |
| &nbsp;&nbsp;↳ `save` | Save generated rules to a file for later use | |
| &nbsp;&nbsp;↳ `load` | Load previously saved rules from a file | |
| &nbsp;&nbsp;↳ `examples` | Run progressive complexity examples demonstrating rule generation | |
| [arbiter](examples/apps/arbiter/) | CLIPS-validated LLM retry app with rule-based answer verification | Rust, Go, CLI/Bash |
| &nbsp;&nbsp;↳ `classification` | Categorize input text into specified categories | |
| &nbsp;&nbsp;↳ `extraction` | Extract structured information from unstructured text | |
| &nbsp;&nbsp;↳ `reasoning` | Perform logical inference and multi-step reasoning | |

<!-- EXAMPLES-TABLE:END -->

## SDK Editions

| Badge | Meaning |
|-------|---------|
| **Community** | Runs with the free OSS SDK |
| **Pro** | Requires a Pro license ([activation guide](https://github.com/nxus-SYSTEMS/nxusKit)) |

See `conformance/example-tiers.json` for the full tier map.

## Project Structure

```
examples/
├── patterns/       Community-tier reusable patterns
├── integrations/   SDK feature combinations
├── apps/           Complete applications (mostly Pro tier)
└── shared/         Shared libraries and helpers (Rust, Go, Python, CLI/Bash)
conformance/        Example manifest and tier definitions
scripts/            Build and test helpers
```

## Building

All examples require the nxusKit SDK. Run these once after cloning:

```bash
# Set up Go workspace, env vars, and native library paths
source ~/.nxuskit/sdk/current/scripts/setup-sdk.sh

# Set up Rust Cargo paths override (generates .cargo/config.toml)
./scripts/setup-sdk-symlink.sh
```

The first script creates Go workspace files and exports environment variables. The second generates a `.cargo/config.toml` that tells Cargo where to find the installed Rust SDK (the generated file is `.gitignore`d — each developer runs this once).

### Rust
```bash
cargo run --manifest-path examples/<category>/<name>/rust/Cargo.toml
```

### Go
```bash
go run -tags nxuskit ./examples/<category>/<name>/go/cmd
```

### Python
```bash
python examples/<category>/<name>/python/main.py
```

### CLI/Bash
```bash
cd examples/<category>/<name>/bash
make run
```

---
<!-- ACKNOWLEDGEMENTS START -->
Built with gratitude for the open-source projects that make nxusKit possible.
See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) for a curated list of key projects.
<!-- ACKNOWLEDGEMENTS END -->

---

## License

nxusKit Examples is dual-licensed under MIT or Apache 2.0, at your option. See [LICENSE](LICENSE), [LICENSE-MIT](LICENSE-MIT), and [LICENSE-APACHE](LICENSE-APACHE).

Copyright 2025-2026 nxus.SYSTEMS LLC.
