# Acknowledgements

**nxusKit Examples** is built on the shoulders of outstanding open-source projects.
We are grateful to their maintainers and contributors.

---

## AI Paradigm Foundations

These projects provide the core AI paradigms that nxusKit wraps and that these examples demonstrate.

### [CLIPS](https://sourceforge.net/projects/clipsrules/)

Decades of expert-system work that makes rule-focused capabilities possible.
License: MIT-0

A word about CLIPS: During its development at NASA from 1985 to 1996, the
primary CLIPS contributors were: Robert Savely, who conceived and championed
the project; Chris Culbert, who managed the project; Gary Riley and Brian
Dantes, who were the lead developers; and Frank Lopez, who developed the first
version. Since leaving NASA in 1996, Gary Riley has maintained CLIPS as public
domain software.

### [Z3 Theorem Prover](https://github.com/Z3Prover/z3)

Microsoft Research's constraint solver powering optimization and satisfiability across our solver examples.
License: MIT

### [zen-engine](https://github.com/gorules/zen)

A blazing-fast business rules engine that powers our decision-table evaluation examples.
License: MIT

### [nalgebra](https://nalgebra.org/)

Linear algebra library enabling the numerical foundations of our Bayesian network implementations.
License: Apache-2.0

### [statrs](https://github.com/statrs-dev/statrs)

Statistical computing library providing probability distributions for Bayesian inference.
License: MIT

### [llama.cpp](https://github.com/ggerganov/llama.cpp)

High-performance LLM inference engine enabling local model support via Ollama and LM Studio.
License: MIT

### [rmcp](https://github.com/nicola-coretech/rmcp)

Rust MCP client/server library enabling Model Context Protocol integration.
License: MIT

### [petgraph](https://github.com/petgraph/petgraph)

Graph data structure library powering Bayesian network structure representation and traversal.
License: MIT/Apache-2.0

### [nuts-rs](https://github.com/pymc-devs/nuts-rs)

No-U-Turn Sampler implementation enabling efficient MCMC sampling in our Bayesian inference examples.
License: MIT

---

## Example-Specific Dependencies

These projects enable specific examples beyond what the SDK provides.

### [gomidi/midi](https://gitlab.com/gomidi/midi)

Go MIDI library enabling music sequence parsing and generation in the riffer example.
License: MIT

### [midly](https://github.com/negamartin/midly)

Rust MIDI parser that makes riffer's music analysis possible.
License: MIT

### [roxmltree](https://github.com/RazrFalcon/roxmltree)

Read-only XML tree parser powering MusicXML support in the riffer example.
License: MIT/Apache-2.0

### [reqwest](https://github.com/seanmonstar/reqwest)

Ergonomic HTTP client enabling direct Ollama REST API integration.
License: MIT/Apache-2.0

### [eframe/egui](https://github.com/emilk/egui)

Immediate-mode GUI framework powering the auth-helper desktop interface.
License: MIT/Apache-2.0

### [crossterm](https://github.com/crossterm-rs/crossterm)

Cross-platform terminal manipulation enabling the interactive example runner.
License: MIT
