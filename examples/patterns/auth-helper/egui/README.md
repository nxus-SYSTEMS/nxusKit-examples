# Auth Helper GUI (egui)

Native desktop credential management for nxusKit providers.

## Edition

**Community** — runs on the OSS / Community SDK edition.

## What this demonstrates

- **Summary:** OAuth login flow and credential management helper
- **Scenario:** List providers, check auth status, set credentials, initiate OAuth flows
- **`tech_tags` in manifest:** `Auth`, `OAuth` — example id **`auth-helper`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md).

1. Build the nxusKit SDK (static-link) if needed:

```bash
cd ../../../../
cargo build --release -p nxuskit-core
```

2. Build this app from `examples/apps/auth-helper/egui`:

```bash
cargo build --release
```

## Run

```bash
cargo run
```

## Features

- **Provider list** with color-coded status indicators (green/yellow/red/gray)
- **Credential form**: set/remove API keys with masked input
- **Dashboard links**: open provider credential pages in browser
- **Toast notifications** for operation feedback
- **Precedence display**: shows credential resolution source (explicit > env > store > none)

## Supported Providers

OpenAI, Claude, Groq, xAI Grok, Ollama, LM Studio, Mistral, Fireworks, Together, OpenRouter, Perplexity.
