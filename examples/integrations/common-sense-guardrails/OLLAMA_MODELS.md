# Curated Ollama Models for Common-Sense Guardrails

This note records the local model pass used for the common-sense guardrails walkthrough on 2026-05-07. It combines `ollama-cache list` SSD residency with `ollama list` installed sizes, then filters to models under 8 GB.

## Source Notes

- Ollama structured outputs are most reliable when the API `format` field carries JSON or a JSON schema, and Ollama recommends grounding the prompt with the schema and using low temperature. The current Bash walkthrough uses `nxuskit-cli call`, which accepts prompt JSON but does not expose Ollama's schema `format` field yet.
- Ollama's Qwen3 model card lists `qwen3:4b` at 2.5 GB and calls out strong instruction following, tool/agent capability, and a thinking mode.
- Ollama's NuExtract model card describes `nuextract` as a 3.8B Phi-3-based information-extraction model.
- Ollama's Llama 3.2 model card lists `llama3.2` / `llama3.2:3b` at 2.0 GB and describes instruction-tuned text models optimized for dialogue, retrieval, and summarization.
- Ollama's Gemma 3 model card lists `gemma3` / `gemma3:4b` at 3.3 GB, with text/image support and a 128K context window.
- Ollama's Mistral NeMo model card lists `mistral-nemo:12b` at 7.1 GB.

References:

- <https://docs.ollama.com/capabilities/structured-outputs>
- <https://ollama.com/library/qwen3>
- <https://ollama.com/library/nuextract>
- <https://ollama.com/library/llama3.2>
- <https://ollama.com/library/gemma3>
- <https://ollama.com/library/mistral-nemo>

## Recommended Walkthrough Models

Use these first because they are SSD-resident locally and under 4 GB:

| Role | Model | Installed size | Why it is on the list | Walkthrough note |
|------|-------|----------------|------------------------|------------------|
| Baseline and repair default | `llama3.2` | 2.0 GB | Small, fast, instruction-tuned dialogue model. | Produced usable baseline and repair prose in local runs; did not produce valid structured facts through prompt-only `nxuskit-cli call`. |
| Alternative baseline and repair | `gemma3` | 3.3 GB | Small model family explicitly shown in Ollama structured-output examples. | Produced usable prose; structured facts still failed without schema-mode enforcement. |
| Experimental facts extractor | `qwen3:4b` | 2.5 GB | Strong instruction following and agent/tool capability; direct JSON probe returned valid JSON. | Not a full-run default because the raw baseline call can exhaust content budget through `nxuskit-cli call`; use phase-specific facts only. |
| Extraction-only experiment | `nuextract` | 2.2 GB | Purpose-built information-extraction model. | Returned JSON-shaped extraction output, but local probe left key scenario facts blank and emitted an end marker. Do not use for full walkthrough. |

Under-8 GB fallback candidates:

| Model | Installed size | Use | Walkthrough note |
|-------|----------------|-----|------------------|
| `mistral:7b` | 4.4 GB | General baseline/repair fallback. | Produced corrected prose, but not structured facts. |
| `mistral-nemo:12b` | 7.1 GB | Larger general model fallback. | Produced good prose, but not structured facts through prompt-only CLI. |
| `qwen3:8b` | 5.2 GB | Stronger Qwen-family candidate. | SSD-resident and under 8 GB, but not selected because smaller Qwen thinking-model probes had raw-call budget issues. |
| `qwen3.5:9b` | 6.6 GB | Larger Qwen-family candidate. | Excluded for walkthrough default after raw-baseline failure through the current CLI path. |

## Current Walkthrough Default

Prefer `llama3.2` for the interactive walkthrough because it is SSD-resident, under 4 GB, and gives readable baseline and repair text quickly. The structured-facts stage is expected to report `fail` until the CLI/SDK path supports provider-native structured-output schema mode or the example adds a stronger extraction strategy.

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=llama3.2
export OLLAMA_HOST=http://127.0.0.1:11434
```

For phase-specific experiments, keep `llama3.2` for prose and try `qwen3:4b` for extraction:

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=llama3.2
export NXUSKIT_COMMON_SENSE_FACTS_MODEL=qwen3:4b
export NXUSKIT_COMMON_SENSE_REPAIR_MODEL=gemma3
export OLLAMA_HOST=http://127.0.0.1:11434
```

## Follow-Up SDK/CLI Need

The local probes suggest that model choice alone is not enough. The robust path is for `nxuskit-cli call` / SDK local-provider calls to expose provider-native structured-output controls, especially Ollama's `format` JSON/schema field, so the facts phase can request a schema rather than relying on prompt-only compliance.
