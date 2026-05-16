# Model Research Harness

Research, test, score, rank, and report on model/provider fitness with a provider-neutral nxusKit workflow.

> Research model fitness with provider-neutral runs, Promptfoo import, deterministic policy checks, Bayesian confidence, and dry-run lifecycle recommendations.

**Scenarios**: `basic-ticket-routing` · `promptfoo-import` · `software-dev`

## Edition

**Community** - the default path uses provider-neutral LLM calls, mock/local fixtures, CLIPS-style deterministic policy checks, Bayesian confidence scoring, Promptfoo import, external-runner adapters, and dry-run lifecycle recommendations. Optional configs can use nxusKit CLIPS and Bayesian engines when native SDK dependencies are installed, with fixture-safe fallbacks for the public quickstart.

**Edition note:** Runs in Community Edition. Future Pro profiles may add Solver portfolio optimization and ZEN decision tables.

**Optional Pro profile** - future solver-backed portfolio selection and ZEN decision-table policies require a Pro or trial entitlement. The public quickstart below does not execute Pro code.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS · BN

- **Summary:** Python-first model research and compatibility harness.
- **Scenario:** Import or define evaluation configs, run provider/model test matrices, score outputs, apply policy, aggregate confidence, and write reports.
- **`tech_tags` in manifest:** `LLM, CLIPS, BN` - example id **`model-research-harness`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only - see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** Python is authoritative. CLI/Bash is a thin wrapper around the Python runner.
- **Python:** standard library only for the public mock quickstart. The bundled `.yaml` configs use a strict JSON-compatible YAML subset; PyYAML is optional for broader user-authored YAML.
- **Native CLIPS/BN:** use a Python interpreter with `cffi` installed and an SDK with `python/src` plus `lib/libnxuskit.dylib`. The harness automatically adds `$NXUSKIT_SDK_DIR/python/src` when `NXUSKIT_SDK_DIR` is set; on macOS, avoid Apple/Xcode Python for native-engine runs unless `cffi` is installed there. Set `NXUSKIT_PYTHON=/path/to/python3` for the Bash wrapper when needed.

## Real-World Applications

| Application | How this example applies |
|-------------|--------------------------|
| Model evaluation | Score model candidates against task-specific outputs and report confidence instead of relying on ad hoc impressions |
| Provider comparison | Compare local and cloud providers through one provider-neutral workflow while keeping capability claims honest |
| Lifecycle policy | Generate dry-run pull, pin, keep, or retest recommendations bounded by deterministic policy |
| Software development workflow research | Exercise code analysis, bug finding, bugfixing, generation, refactoring, and review scenarios with public-safe fixtures |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/model-research-harness`:
cd python && python3 main.py --help
cd bash && bash main.sh --help
```

## Run

Mock mode uses checked-in fixtures. It does not require cloud credentials, Promptfoo, Ollama, or a Pro entitlement.

```bash
cd python
python3 main.py --config ../configs/nxuskit-harness-basic.yaml --mode mock --json
python3 main.py --config ../configs/nxuskit-harness-software-dev.yaml --mode mock --output-dir ../.tmp/software-dev
```

Thin CLI/Bash wrapper:

```bash
cd bash
bash main.sh --config ../configs/nxuskit-harness-basic.yaml --mode mock --json
```

Promptfoo import:

```bash
cd python
python3 main.py --import-promptfoo ../configs/promptfoo-basic.yaml --mode import-promptfoo --json

python3 main.py \
  --import-promptfoo ../configs/promptfoo-requires-code.yaml \
  --compatibility-report ../.tmp/promptfoo-requires-code-report.json \
  --json
```

The second command is intentionally fail-closed: it writes a compatibility report that requires `--allow-code` or `--promptfoo-native-reference`.

## Configs

| Config | Purpose |
|--------|---------|
| `nxuskit-harness-basic.yaml` | Minimal mock quickstart for ticket classification |
| `nxuskit-harness-clips-policy.yaml` | Deterministic CLIPS-style required-field and forbidden-value checks |
| `nxuskit-harness-clips-engine.yaml` | Real nxusKit `ClipsSession` policy execution with Python fallback when native CLIPS is unavailable |
| `nxuskit-harness-bayesian-confidence.yaml` | Posterior confidence from sparse weighted evidence |
| `nxuskit-harness-bn-engine.yaml` | Real nxusKit BN inference over model-fitness evidence with beta fallback when native BN is unavailable |
| `nxuskit-harness-local-vs-cloud.yaml` | Local fixture versus cloud-reference fixture comparison |
| `nxuskit-harness-structured-output.yaml` | Native JSON-mode claims versus harness-side schema validation |
| `nxuskit-harness-lifecycle-policy.yaml` | Dry-run cache and lifecycle recommendations |
| `nxuskit-harness-lifecycle-mutation-fixture.yaml` | Public-safe mutation gate fixture requiring both external and lifecycle approval flags |
| `nxuskit-harness-matrix-template.yaml` | Compact prompt/parameter matrix expansion syntax |
| `nxuskit-harness-native-ollama-template.yaml` | Native Ollama schema, image, thinking, and tool-call knobs behind harness scoring |
| `nxuskit-harness-software-dev.yaml` | Code analysis, bug finding, bugfixing, code generation, refactoring, and review scenarios |
| `nxuskit-harness-external-command-fixture.yaml` | Public-safe fixture contract for wrapping operational runners |
| `nxuskit-harness-devops-ollama-parity.yaml` | Opt-in local adapter shape for a private Ollama research harness checkout |
| `promptfoo-basic.yaml` | Promptfoo-compatible config that imports and runs |
| `promptfoo-requires-code.yaml` | Promptfoo config that requires explicit trust or native-reference mode |

Test blocks may include a `matrix` object to expand variants without duplicating config:

```json
{
  "id": "format-{{ prompt_variant }}-think-{{ think }}",
  "matrix": {
    "prompt_variant": ["baseline", "strict"],
    "think": ["off", "low"]
  }
}
```

Each combination is merged into `test.vars`, so prompts, ids, and adapter placeholders can reference the generated values.

## Operational Adapter Mode

The harness can wrap existing operational research runners through explicit external-command tests. This is useful when a team already has domain-specific scripts for local Ollama inventory, structured extraction, image/document pipelines, cache policy, or row-level fixture scoring.

External commands are fail-closed and never run unless `--allow-external` is supplied:

```bash
cd python
python3 main.py \
  --config ../configs/nxuskit-harness-external-command-fixture.yaml \
  --allow-external \
  --json
```

The fixture config runs only checked-in deterministic fixture commands. The DevOps parity config is a template for private/local use and expects `OLLAMA_MODEL_TESTING_ROOT` to point at an existing `ollama-model-testing` checkout:

```bash
export OLLAMA_MODEL_TESTING_ROOT=/path/to/ollama-model-testing
cd python
python3 main.py \
  --config ../configs/nxuskit-harness-devops-ollama-parity.yaml \
  --allow-external \
  --only-test common-sense-carwash \
  --output-dir ../.tmp/devops-parity
```

Use `--exclude-test` to skip expensive tests from a larger config. Both `--only-test` and `--exclude-test` accept comma-separated ids and may be repeated.

The public adapter normalizes DevOps-style report shapes for common-sense curation, prompted/native tool intent, direct structured extraction, two-stage OCR or VLM pipelines, safe-labs row-level scoring, and CSV/TSV comparison helpers. The DevOps parity template also includes non-mutating `ollama-cache status`, `list`, and `plan-evict` checks.

External lifecycle mutation such as pulling, removing, pinning, or evicting models requires a test with `external_command.mutation: true` and both flags:

```bash
python3 main.py \
  --config ../configs/nxuskit-harness-lifecycle-mutation-fixture.yaml \
  --allow-external \
  --allow-lifecycle-mutations
```

Public configs should keep mutation commands behind explicit customer policy bounds.

## Output

Each run can write:

- `result.json`
- `summary.md`
- Promptfoo compatibility report when importing Promptfoo configs
- Scenario-level pass/fail matrix
- Provider/model recommendation table
- Capability truth table

The capability truth table separates native provider guarantees from harness-side validation and repair. For v0.9.4, Groq remains provider id `groq` with `GROQ_API_KEY`; xAI Grok uses provider id `xai` with `XAI_API_KEY`.

## Live Mode

Live mode uses nxusKit provider factories for `ollama`, `lmstudio`, `openai`, `claude`, `groq`, and `xai` when credentials or local services are configured:

```bash
cd python
python3 main.py --config ../configs/nxuskit-harness-basic.yaml --mode live --provider ollama --model llama3.2
```

Strict schema support, native tool calling, and thinking controls vary by provider and model. The harness reports those differences instead of treating every backend as equivalent.

For Ollama features that are not yet normalized across every provider, set `native_ollama: true` on the provider or test. That path uses Ollama's local `/api/chat` API directly and supports `schema`/JSON `format`, `think`, `tools`, image files, `options`, and `num_predict`. If an Ollama build rejects the `think` field, the harness retries once without it and records the observed metadata.

## Promptfoo Compatibility

Portable Promptfoo configs import directly. Prompt/provider matrices expand to harness tests. Configs with executable or provider-native behavior fail closed unless the caller acknowledges the trust boundary:

```bash
python3 main.py --import-promptfoo ../configs/promptfoo-requires-code.yaml --allow-code --json
python3 main.py --import-promptfoo ../configs/promptfoo-requires-code.yaml --promptfoo-native-reference --json
```

With `--allow-code`, JavaScript assertions are executed through `node` when available. Unsupported assertions still fail closed instead of silently disappearing from the score.

## nxusKit Engine Hooks

The default configs are fixture-safe and run with stdlib Python. Engine configs demonstrate how the same harness can call nxusKit-native reasoning providers:

- `policy.engine: "nxuskit-clips"` loads a CLIPS rules file through `ClipsSession`, asserts the model output as a fact, and converts emitted finding facts into policy dispositions. `on_engine_unavailable: "fallback-python"` keeps public smoke tests runnable when native CLIPS dependencies are not installed.
- `bayesian.engine: "nxuskit-bn"` loads a BIF model through nxusKit BN, maps test scores into evidence, and queries a configured posterior. `on_engine_unavailable: "fallback-beta"` keeps reports useful on machines without native BN dependencies.

Native-engine smoke example:

```bash
export NXUSKIT_SDK_DIR="${NXUSKIT_SDK_DIR:-$HOME/.nxuskit/sdk/current}"
export NXUSKIT_LIB_PATH="$NXUSKIT_SDK_DIR/lib/libnxuskit.dylib"

# Pick a Python with cffi installed. On this development Mac, Homebrew Python works.
/opt/homebrew/bin/python3 -c "import cffi"

/opt/homebrew/bin/python3 python/main.py \
  --config configs/nxuskit-harness-clips-engine.yaml \
  --json

/opt/homebrew/bin/python3 python/main.py \
  --config configs/nxuskit-harness-bn-engine.yaml \
  --json
```

## Release Notes For Review

- Python is the authoritative implementation. Bash remains a thin wrapper for automation-friendly entry points.
- Promptfoo import covers common portable config shapes, prompt/provider matrices, explicit trust gates for code/native behavior, and JavaScript assertion execution under `--allow-code`.
- CLIPS and Bayesian examples include both deterministic/fallback checks and opt-in nxusKit-native engine execution.
- Operational parity is provided through explicit external-command adapters, not private baked-in assumptions. Public releases should keep private rankings, fixture paths, and cache policy defaults out of bundled configs.
- Lifecycle mutation remains blocked unless both `--allow-external` and `--allow-lifecycle-mutations` are supplied, and customer auto-approval should be bounded in config.
