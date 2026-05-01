# Streaming with Token Budget Pattern

Demonstrates cost control by enforcing token limits during streaming responses.

> Stop paying for tokens you don't need — enforce real-time streaming budgets and cancel LLM requests the moment your limit is reached.

## Edition

**Community** — runs on the OSS / Community SDK edition.

## What this demonstrates

**Difficulty: Starter** 🟢 · LLM

- **Summary:** Token budget management and cost estimation
- **Scenario:** Track and limit token usage across requests
- **`tech_tags` in manifest:** `LLM` — example id **`token-budget`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, python, rust, bash (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **Models:** CLI/Bash defaults to the `loopback` provider for credential-free smoke tests. Set cloud provider API keys or run **Ollama** locally when using live providers in the **Run** steps.

## Key nxusKit Features Demonstrated

| Feature | Description |
|---------|-------------|
| **Unified Streaming** | Same streaming interface across all providers (Stream in Rust, channels in Go) |
| **Stream Cancellation** | Graceful cancellation supported by all provider implementations |
| **Token Tracking** | Normalized token usage in final chunk regardless of provider |

**Provider Compatibility**: Any provider supporting streaming (Claude, OpenAI, Ollama)

## Pattern Overview

When streaming LLM responses, you may want to stop generation early to control costs or enforce response length limits. This pattern monitors token usage during streaming and cancels the request when a budget is reached.

## Key Features

- Real-time token estimation during streaming
- Graceful stream cancellation when budget exceeded
- Returns partial content and budget status
- Works with any streaming-capable provider

## Real-World Application

Usage metering, per-user quota enforcement.

## Technologies

LLM

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |
| Python | `python/` | Available |
| CLI/Bash | `bash/` | Available |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/patterns/token-budget`:
cd rust && cargo build
cd go && make build
cd python && python3 main.py --help
cd bash && make build
```
## Token Estimation

Since exact token counts aren't available during streaming, we use a simple heuristic:
- ~4 characters per token (works well for English text)
- Adjust this ratio for other languages or specialized content

## Library usage

### Rust

```rust
use token_budget::stream_with_budget;

// Stream with a 100 token budget
let result = stream_with_budget(&provider, &request, 100).await?;

println!("Content: {}", result.content);
println!("Tokens used: {}", result.estimated_tokens);
if result.budget_reached {
    println!("Budget limit reached - response truncated");
}
```

### Go

```go
// Stream with a 100 token budget
result, err := StreamWithBudget(ctx, provider, req, 100)

fmt.Println("Content:", result.Content)
fmt.Println("Tokens used:", result.EstimatedTokens)
if result.BudgetReached {
    fmt.Println("Budget limit reached - response truncated")
}
```

## Run

### Rust
```bash
cd rust
cargo run
```

### Go
```bash
cd go
go run .
```

### Python
```bash
cd python
python3 main.py
```

### CLI/Bash
```bash
cd bash
make run
TOKEN_BUDGET_MAX=40 make run ARGS="ollama"
```

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
go run . --verbose          # Go
make run ARGS="--verbose"  # CLI/Bash

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
go run . --step             # Go
make run ARGS="--step"     # CLI/Bash

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
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

# Python smoke
cd python && python3 main.py --help

# CLI/Bash
cd bash && make test
```

## Production Considerations

1. **Calibrate token ratio**: Adjust the 4 chars/token estimate for your specific use case
2. **Buffer margin**: Set budget slightly below hard limits to account for estimation error
3. **User feedback**: Indicate when responses are truncated due to budget
4. **Combine with max_tokens**: Use both streaming budget and API max_tokens for defense in depth
