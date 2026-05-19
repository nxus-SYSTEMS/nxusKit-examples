# Common-Sense Guardrails

> Catch plausible but impossible LLM recommendations by turning answers into facts, firing rules, and repairing failures with auditable prompts.

**Scenarios**: `car-wash` · `coupon-stack` · `pallet-door` · `cold-chain`

## Edition

**Community** - runs the full guardrail workflow: raw answer, structured facts, CLIPS validation, deterministic repair packet, and corrected answer.

**Edition note:** Runs in Community Edition. Pro adds optional Solver and ZEN proof stages.

## Pro Enhancement Path

Pro adds optional proof stages only when requested with `--stage pro` or `--stage all`.

- `solver-proof`: uses Solver artifacts for object-presence and dimensional feasibility scenarios.
- `zen-policy`: uses ZEN decision artifacts for promotion policy and cold-chain handling scenarios.

Mock Pro evidence is fixture-backed and does not require entitlement. In live mode this example checks for the normal nxusKit Pro entitlement signal before labeling a Pro proof stage as live-entitled; without entitlement it skips the Pro stage with a clear message and leaves Community stages runnable. The first-release Python and Bash implementations do not execute Solver or ZEN engines directly; they show the handoff shape through checked-in proof artifacts.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS

- **Summary:** Progressive LLM guardrails with Community CLIPS validation and optional Pro proof stages.
- **Scenario:** Refine LLM recommendations with structured extraction, rules, retry repair, and optional Pro proof.
- **`tech_tags` in manifest:** `LLM`, `CLIPS` - example id **`common-sense-guardrails`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Mock mode uses only Python 3, Bash, and `jq`. Live mode uses an installed nxusKit SDK or `nxuskit-cli`.
- **Languages in this example:** python, bash.
- **Models:** Live and auto mode can use `NXUSKIT_PROVIDER` with `NXUSKIT_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, reachable `OLLAMA_HOST`, or reachable `LMSTUDIO_BASE_URL`.
- **CLIPS:** Community validation is represented by scenario-local CLIPS rule files and normalized findings.

## Scenario Purposes

| Scenario | Failure class | Guardrail |
|----------|---------------|-----------|
| `car-wash` | Implicit object-presence precondition | Washing the car requires the car to be at the wash location, not just the person. |
| `coupon-stack` | Promotion policy and margin violation | Discounts, free shipping, and loyalty credits must satisfy stacking and margin rules. |
| `pallet-door` | Dimensional feasibility and unsafe geometry | A pallet cannot be pushed through a door that is narrower than the loaded pallet. |
| `cold-chain` | Handling and auditability violation | Frozen medical material must use certified refrigerated service with temperature traceability. |

## Run

Canonical Community smoke commands:

```bash
cd examples/integrations/common-sense-guardrails/python
python3 main.py --scenario car-wash --mode mock --stage ce

cd ../bash
bash main.sh --scenario car-wash --mode mock --stage ce
```

Machine-readable parity checks:

```bash
cd examples/integrations/common-sense-guardrails/python
python3 main.py --scenario car-wash --mode mock --stage all --json

cd ../bash
bash main.sh --scenario car-wash --mode mock --stage all --json
```

All launch scenarios:

```bash
for scenario in car-wash coupon-stack pallet-door cold-chain; do
  python3 main.py --scenario "$scenario" --mode mock --stage ce --json
done
```

## Mode Behavior

- `--mode mock`: uses checked-in fixtures for every Community stage and optional Pro evidence. It performs no provider, network, or entitlement preflight.
- `--mode live`: requires a configured live provider and fails before scenario content is sent if preflight is unavailable.
- `--mode auto`: uses live execution when provider preflight succeeds; otherwise it labels the run as fixture-backed mock mode.

Live structured fact extraction prefers pure JSON. If the model wraps a valid JSON object in prose, the runners extract it and mark the structured-facts stage as `warn`; if no valid JSON object is recoverable after retry, the structured-facts stage is marked `fail` and the run falls back to checked-in fact fixtures so later guardrail stages can still show their behavior.

Provider preflight order is explicit nxusKit provider/model environment, phase-specific model environment, nxusKit-recognized cloud credentials, reachable Ollama, then reachable LM Studio. Do not commit provider credentials or license tokens.

For local Ollama live runs, the Python runner honors `OLLAMA_HOST` and uses a short 5 second connect timeout with a 120 second read timeout because local model responses can be slower than cloud providers. The Bash runner forwards model settings to `nxuskit-cli call`; CLI timeout behavior comes from the installed SDK.

Live runs can use one provider/model for every phase or override phases independently:

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
```

Phase-specific provider overrides are also supported with `NXUSKIT_COMMON_SENSE_BASELINE_PROVIDER`, `NXUSKIT_COMMON_SENSE_FACTS_PROVIDER`, and `NXUSKIT_COMMON_SENSE_REPAIR_PROVIDER`. See [OLLAMA_MODELS.md](./OLLAMA_MODELS.md) for local Ollama model notes from the repository walkthrough.

## Local Model Starting Points

These are dated smoke-test starting points from the DevOps Ollama model-testing notes, not model rankings or product guarantees.

| Model | Why try it |
|-------|------------|
| `qwen3.5:4b` | 2026-05-11/12 local smokes show the desired guardrail-demo shape: naive car-wash answer fails as `walk`, constrained output is parseable, and enhanced object-presence prompting recovers to `drive`; it also has local structured/document evidence. |
| `qwen3.5:2b` | 2026-05-12 local smoke shows the same fail/recover car-wash shape at a smaller 2.7 GB footprint; use it when low-resource local testing matters more than tool-intent strength. |
| `gemma3:1b` or `erukude/omni-json:1b` | 2026-05-09/12 small-model smokes found both useful for very small guardrail demos because they reproduce the naive failure and recover under the enhanced prompt. |
| `nemotron-3-nano:4b` | 2026-05-12 smokes show the car-wash fail/recover target plus a native strict tool-call pass, making it a useful local comparison point. |

Avoid using passing or unparsed baseline behavior as a demo failure source. For example, the same DevOps notes show `phi4-mini-reasoning:3.8b` answering `drive` on the naive prompt and `granite4:350m-h` failing to recover under the enhanced prompt, so neither is a good default for this specific guardrail walkthrough.

## Scenario Data Contract

Each scenario directory contains these required Community files:

```text
problem.json
expected-output.json
rules.clp
mock-baseline.json
mock-facts.json
mock-repair.json
mock-corrected.json
```

Pro-enabled scenarios add one of:

```text
solver-problem.json
decision-model.json
```

Structured fact fixtures must include:

- `goal`
- `candidate_actions`
- `objects_required`
- `objects_moved`
- `resources`
- `constraints`
- `policy_context`
- `confidence`

CLIPS findings normalize to `status`, `rule_id`, `severity`, `message`, and `evidence`. Expected-output fixtures list required stage ids, expected finding rule ids, correction text fragments, and optional Pro stage metadata.

## Adding a Scenario

1. Create `scenarios/<name>/`.
2. Add every required Community file listed above.
3. Include a stable `id`, non-empty prompts, and a `repair_template` containing `{findings}` in `problem.json`.
4. Add scenario-local `rules.clp` findings with stable kebab-case rule ids.
5. Add `solver-problem.json` or `decision-model.json` only when the optional Pro stage is meaningful.
6. Run validation and both contract test suites before updating manifest scenarios.

Authoring validation:

```bash
cd examples/integrations/common-sense-guardrails/python
python3 main.py --validate-scenarios
python3 test_contract.py

cd ../bash
bash main.sh --validate-scenarios
bash test.sh
```

## Public Inspiration

Shout-out to [Haris Rahi](https://harisrahi.ai) and [Tamara Storm](https://www.linkedin.com/in/tamarastorm) for their LinkedIn discussions on the car-wash scenario from Opper.ai, Focus AI, and the HOB benchmark line.

## Scope Exclusions

This is not a medical, legal, financial, or safety certification system. Do not add PHI, regulated personal data, certification claims, or model-ranking claims to scenarios. The examples demonstrate an engineering pattern for auditable guardrails, not a complete common-sense benchmark.

## Real-World Applications

| Application | How this example applies |
|-------------|--------------------------|
| LLM answer validation | Catch plausible recommendations that fail physical, operational, or policy preconditions before they reach users |
| Policy enforcement | Turn free-form answers into facts, apply deterministic rules, and produce auditable repair context |
| Operational decision support | Preserve fast LLM drafting while requiring concrete feasibility evidence for workflow-critical recommendations |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`: extracted bundle or installer layout) for live SDK checks. Mock acceptance commands do not need the SDK.

```bash
# From `/examples/integrations/common-sense-guardrails`:
cd python && python3 main.py --help
cd ../bash && make test
```
