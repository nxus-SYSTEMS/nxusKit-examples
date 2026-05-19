# Curated Ollama Models for Common-Sense Guardrails

This note records local model passes used for the common-sense guardrails walkthrough. The first pass on 2026-05-07 combined `ollama-cache list` SSD residency with `ollama list` installed sizes and filtered to models under 8 GB. Follow-up passes on 2026-05-11 and 2026-05-12 added the car-wash fail/recover smoke shape and structured-output checks.

These are dated smoke-test starting points, not model rankings or product guarantees.

## Source Notes

- Live structured fact extraction prefers pure JSON. If the model wraps a valid JSON object in prose, the Python and Bash runners extract it and mark the structured-facts stage as `warn`. If no valid JSON object is recoverable after retry, the stage is marked `fail` and the run falls back to checked-in fact fixtures so later guardrail stages can still demonstrate their behavior.
- Ollama structured outputs are most reliable when the API `format` field carries JSON or a JSON schema, and Ollama recommends grounding the prompt with the schema and using low temperature. Provider-native structured-output controls are still the robust path for future hardening, but this walkthrough no longer treats structured-facts failure as the expected result.
- Local car-wash smokes found `qwen3.5:4b` to be the best primary walkthrough candidate: small enough for local proof, stronger than the 2B option, and tested against the desired naive `walk` failure plus enhanced `drive` recovery.
- Local car-wash smokes found `qwen3.5:2b` useful as the low-resource option with the same fail/recover shape.
- Small-model smokes also found `gemma3:1b` and `erukude/omni-json:1b` useful for very small demos. `nemotron-3-nano:4b` is useful as a comparison point because separate tool-intent smokes showed native strict behavior.
- `llama3.2` remains a historical target candidate from earlier sweeps, but it is no longer the default recommendation for this walkthrough.

References:

- <https://docs.ollama.com/capabilities/structured-outputs>
- <https://ollama.com/library/llama3.2>
- <https://ollama.com/library/gemma3>
- DevOps Ollama model-testing notes from 2026-05-09 through 2026-05-12

## Recommended Walkthrough Models

Use these first because they are small local smoke-test candidates that match the guardrail demo shape:

| Role | Model | Installed size | Why it is on the list | Walkthrough note |
|------|-------|----------------|------------------------|------------------|
| Primary live walkthrough | `qwen3.5:4b` | 3.4 GB | Stronger small Qwen 3.5 option from the 2026-05-11/12 local smokes. | Desired car-wash shape: naive answer fails as `walk`, constrained output is parseable, and enhanced object-presence prompting recovers to `drive`. Use this first when available. |
| Low-resource walkthrough | `qwen3.5:2b` | 2.7 GB | Smaller Qwen 3.5 option from the 2026-05-12 local smoke. | Same fail/recover car-wash shape at a smaller footprint. Use when local resource constraints matter more than maximum tool-intent strength. |
| Very small demo candidates | `gemma3:1b` or `erukude/omni-json:1b` | 815 MB / 1.4 GB | Very small models that reproduced the demo failure and recovery shape in local smokes. | Useful for constrained machines, but keep the primary docs and article proof centered on `qwen3.5:4b`. |
| Comparison candidate | `nemotron-3-nano:4b` | 2.8 GB | Car-wash fail/recover target plus separate native strict tool-call smoke evidence. | Interesting for comparison, but adding it to the main walkthrough can dilute the guardrails story. |

Other observed models:

| Model | Installed size | Use | Walkthrough note |
|-------|----------------|-----|------------------|
| `llama3.2` | 2.0 GB | Historical target candidate. | Earlier local sweeps showed a valid fail/recover shape, but newer release-surface guidance prefers `qwen3.5:4b` primary and `qwen3.5:2b` low-resource. |
| `phi4-mini-reasoning:3.8b` | 3.2 GB | Avoid as default for this scenario. | Answered `drive` on the naive prompt, which removes the intended baseline failure. |
| `granite4:350m-h` | 366 MB | Avoid as default for this scenario. | Failed to recover under the enhanced prompt in local smokes. |
| `qwen3:4b` | 2.5 GB | Historical extraction experiment. | Direct JSON probes were useful, but newer Qwen 3.5 smokes are the better starting point for the full walkthrough. |

## Current Walkthrough Default

Prefer `qwen3.5:4b` for the interactive walkthrough when it is available. It is the primary v0.9.4 local proof candidate, remains small enough for a developer laptop, and has current local smoke evidence for the car-wash fail/recover shape.

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
```

For a lower-resource run, use the 2B Qwen 3.5 variant:

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=qwen3.5:2b
export OLLAMA_HOST=http://127.0.0.1:11434
```

For phase-specific experiments, keep the stronger model on extraction and repair while trying a smaller baseline:

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=qwen3.5:2b
export NXUSKIT_COMMON_SENSE_FACTS_MODEL=qwen3.5:4b
export NXUSKIT_COMMON_SENSE_REPAIR_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
```

## Structured Facts Posture

Provider-native structured-output controls remain the preferred hardening path, especially Ollama JSON/schema formatting and thinking-mode controls when exposed through the installed SDK/CLI surface. The example itself should be described more narrowly: live structured facts can pass with pure JSON, warn when valid JSON is recovered from prose, or fail after retry and fall back to fixtures. Failure is a fallback state, not the expected walkthrough result.
