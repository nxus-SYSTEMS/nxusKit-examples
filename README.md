# nxusKit Examples

**[nxus.SYSTEMS](https://nxus.systems)** · **[Examples Portfolio](https://nxus.systems/examples)** · **[nxusKit SDK](https://github.com/nxus-SYSTEMS/nxusKit)**

32 production examples for the nxusKit SDK in Rust, Go, and Python — covering LLM patterns, CLIPS rule engines, Z3 constraint solvers, Bayesian networks, and ZEN decision tables.

## Quick Start

```bash
# 1. Install the SDK (see nxusKit Getting Started guide)
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
| [multi-provider](examples/patterns/multi-provider/) | Using multiple providers in one application | Rust, Go, Python |
| [convenience-api](examples/patterns/convenience-api/) | LiteLLM-style convenience API usage | Rust, Go |
| [blocking-api](examples/patterns/blocking-api/) | Synchronous blocking API for simpler use cases | Rust, Go |
| [capability-detection](examples/patterns/capability-detection/) | Detecting provider capabilities at runtime | Rust, Go |
| [cost-routing](examples/patterns/cost-routing/) | Cost-aware provider routing and selection | Rust, Go, Python |
| [polymorphic](examples/patterns/polymorphic/) | Polymorphic provider patterns with trait objects | Rust, Go |
| [retry-fallback](examples/patterns/retry-fallback/) | Retry and fallback strategies across providers | Rust, Go, Python |
| [structured-output](examples/patterns/structured-output/) | JSON mode and structured output generation | Rust, Go, Python |
| [timeout-config](examples/patterns/timeout-config/) | Timeout configuration and connection management | Rust, Go, Python |
| [token-budget](examples/patterns/token-budget/) | Token budget management and cost estimation | Rust, Go, Python |
| [vision](examples/patterns/vision/) | Vision and multimodal capabilities with images | Rust, Go, Python |
| [auth-helper](examples/patterns/auth-helper/) | OAuth login flow and credential management helper | Rust, Go |
| &nbsp;&nbsp;↳ `status` | List provider authentication status and stored credentials | |
| &nbsp;&nbsp;↳ `set` | Store an API key for a specific provider | |
| &nbsp;&nbsp;↳ `remove` | Remove a stored API key for a provider | |
| &nbsp;&nbsp;↳ `dashboard` | Open provider credential dashboard in browser | |
| [solver](examples/patterns/solver/) | Z3 constraint solver integration via nxusKit SDK | Rust, Go, Python |
| &nbsp;&nbsp;↳ `theme-park` | Budget and space planning for a theme park with rides, food courts, and entertainment zones | |
| &nbsp;&nbsp;↳ `space-colony` | Resource allocation for a space colony dealing with solar storm what-if scenarios | |
| &nbsp;&nbsp;↳ `fantasy-draft` | Fantasy sports draft optimization under salary cap with injury what-if analysis | |
| [bayesian-inference](examples/patterns/bayesian-inference/) | Bayesian network inference via nxusKit SDK | Rust, Go, Python |
| &nbsp;&nbsp;↳ `haunted-house` | Investigate a haunted house — is it a ghost or a raccoon? | |
| &nbsp;&nbsp;↳ `coffee-shop` | Diagnose bad espresso from grind size, temperature, and bean age | |
| &nbsp;&nbsp;↳ `plant-doctor` | Diagnose a sick plant from overwatering, nutrient, and disease evidence | |
| [solver-what-if](examples/patterns/solver-what-if/) | What-if scenario analysis with solver scoping | Rust, Go, Python |
| &nbsp;&nbsp;↳ `wedding` | Wedding budget planning with $25k constraint and vendor what-if scenarios | |
| &nbsp;&nbsp;↳ `mars` | Mars colony resource allocation with dust storm what-if disruptions | |
| &nbsp;&nbsp;↳ `recipe` | Recipe scaling with vegan substitution — may be UNSAT | |

### Integrations — Combining SDK features

| Example | Description | Languages |
|---------|-------------|-----------|
| [ollama](examples/integrations/ollama/) | Using Ollama for local inference | Rust, Go, Python |
| [lmstudio](examples/integrations/lmstudio/) | Using LM Studio for local inference | Rust, Go |
| [alert-triage](examples/integrations/alert-triage/) | Alert triage with LLM-powered analysis | Rust, Go |
| [cli-assistant](examples/integrations/cli-assistant/) | Interactive CLI assistant with LLM backend | Rust, Go |
| [clips-basics](examples/integrations/clips-basics/) | CLIPS rule engine basics via nxusKit SDK | Rust, Go |
| [clips-llm-hybrid](examples/integrations/clips-llm-hybrid/) | Hybrid CLIPS rules + LLM reasoning | Rust, Go, Python |
| [bn-solver-clips-pipeline](examples/integrations/bn-solver-clips-pipeline/) | Three-stage BN prediction → Solver optimization → CLIPS safety pipeline | Rust, Go |
| &nbsp;&nbsp;↳ `festival` | Music festival staging — crowd predictions drive band scheduling and safety | |
| &nbsp;&nbsp;↳ `rescue` | Search and rescue — survivor probability drives team assignment and safety checks | |
| &nbsp;&nbsp;↳ `bakery` | Bakery scheduling — demand forecasts drive oven allocation and allergen separation | |
| [llm-solver-hybrid](examples/integrations/llm-solver-hybrid/) | Hybrid LLM + Z3 solver problem solving | Rust, Go, Python |
| &nbsp;&nbsp;↳ `seating` | Wedding dinner seating — 12 guests across 3 tables with constraints | |
| &nbsp;&nbsp;↳ `dungeon` | Dungeon layout — 5 rooms with boss and treasure placement rules | |
| &nbsp;&nbsp;↳ `road-trip` | Road trip planning — 14 days across 5 national parks with preferences | |
| [bn-structure-learning](examples/integrations/bn-structure-learning/) | Bayesian network structure learning from data | Rust, Go, Python |
| &nbsp;&nbsp;↳ `golf` | Golf course conditions — weather, soil, and maintenance factor learning | |
| &nbsp;&nbsp;↳ `bmx` | BMX performance — skill level, technique, and jump factor learning | |
| &nbsp;&nbsp;↳ `sourdough` | Sourdough baking — feeding schedule, flour type, and temperature factor learning | |
| [zen-decisions](examples/integrations/zen-decisions/) | ZEN decision table evaluation via nxusKit SDK | Rust, Go, Python |
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
| [ruler](examples/apps/ruler/) | LLM-powered CLIPS rule generator with automatic validation | Rust, Go |
| &nbsp;&nbsp;↳ `generate` | Generate CLIPS rules from natural language descriptions | |
| &nbsp;&nbsp;↳ `validate` | Validate CLIPS rule syntax and semantic correctness | |
| &nbsp;&nbsp;↳ `save` | Save generated rules to a file for later use | |
| &nbsp;&nbsp;↳ `load` | Load previously saved rules from a file | |
| &nbsp;&nbsp;↳ `examples` | Run progressive complexity examples demonstrating rule generation | |
| [arbiter](examples/apps/arbiter/) | CLIPS-validated LLM retry app with rule-based answer verification | Rust, Go |
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
└── shared/         Shared libraries (Rust, Go, interactive utilities)
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

## Acknowledgements

These examples build on outstanding open-source projects. See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) for the full list, and [NOTICE](NOTICE) for third-party license details.

## License

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE).
