# CLIPS Basics

Load rules, assert facts, and run the CLIPS inference engine

> Bring deterministic rule-based logic to your applications by driving the CLIPS inference engine directly through the nxusKit SDK.

## Edition

**Community** — runs on the OSS / Community SDK edition.

## What this demonstrates

**Difficulty: Intermediate** 🟦 · CLIPS

- **Summary:** CLIPS rule engine basics via nxusKit SDK
- **Scenario:** Load rules, assert facts, and run the CLIPS inference engine
- **`tech_tags` in manifest:** `CLIPS` — example id **`clips-basics`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## CLIPS integration path

This example uses **provider chat**: JSON shaped like `ClipsInput` is sent as the user message body to the CLIPS `LLMProvider`, and the engine returns `ClipsOutput` JSON in `response.content`. Local wire types mirror that contract and are **not** SDK exports: Go `go/clips_wire.go`, Rust via shared crate `examples/shared/clips-wire-rust` (`nxuskit-examples-clips-wire`), Python reference `examples/shared/python/clips_wire.py`.

For **Session API** access (load rules, assert facts, run, inspect via handles), use `nxuskit::ClipsSession`, `nxuskit.ClipsSession`, or the C ABI in the SDK bundle.

Schema reference: `conformance/clips-json-contract.json` in this repository. Full field documentation: nxusKit SDK `sdk-packaging/docs/rule-authoring.md` — **ClipsInput JSON Reference** (heading anchor `#clipsinput-json-reference`; in the extracted bundle, see `docs/rule-authoring.md`).

## Real-World Application

Business rules engine, compliance checking

## Technologies

CLIPS

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |
| Python | `examples/shared/python/clips_wire.py` | Wire types only (use with nxuskit-py provider chat) |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/clips-basics`:
cd rust && cargo build
cd go && make build
```

Cross-language parity: the **animal classification** demos use the same `ClipsInput`-shaped JSON (`facts` → `template` / `values`) in Go (`main.go` example 1 dog; example 2 Frog/Penguin/Spider batch) and Rust (`animal_classification.rs` via `ClipsInputWire`).

## Run

### Rust
```bash
cd rust
cargo run
```

### Go
```bash
cd go
make build && bin/clips-basics
```
