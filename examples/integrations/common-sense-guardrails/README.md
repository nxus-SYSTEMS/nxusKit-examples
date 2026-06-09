# Common-Sense Guardrails

> Catch plausible but impossible LLM recommendations by turning answers into facts, firing rules, and repairing failures with auditable prompts.

**Scenarios**: `car-wash` · `coupon-stack` · `pallet-door` · `cold-chain`

## Edition

**Community** - runs the selected guardrail workflow with CLIPS available in CE: raw answer, structured facts, guardrail findings, deterministic repair packet, corrected answer, and reevaluation.

**Edition note:** Runs in Community Edition with CLIPS and selected BN risk scoring. Pro adds Solver/Z3 and ZEN guardrails for repair feedback when selected.

## Pro Enhancement Path

Guardrails are selected with `--guardrails`. The default selection is `auto`, which includes CLIPS, the scenario's Pro mechanism when that mechanism is available, and BN risk scoring for scenarios where uncertainty is meaningful. `--stage ce|pro|all` remains as a compatibility alias for existing smoke commands.

- `clips`: Community rule checks over typed facts. Best for explicit scenario rules and explainable findings.
- `bn`: Community Bayesian Network inference over noisy or partial evidence. Used only for `coupon-stack` and `cold-chain`.
- `solver` / `z3`: Pro constraint feasibility. Used for object-presence and dimensional feasibility scenarios.
- `zen`: Pro decision-table and policy admissibility. Used for promotion policy and cold-chain handling scenarios.

Mock Pro and BN findings are fixture-backed and do not require entitlement. Mock output is explicitly labeled with `mechanism_source: "fixture"` and `runtime_executed: false`. In live mode, explicit Pro guardrail selection requires Pro entitlement and calls `nxuskit-cli solver solve` or `nxuskit-cli zen eval`; explicit BN selection calls `nxuskit-cli bn infer`. In `--guardrails auto`, unavailable Pro guardrails downgrade with a warning and the Community CLIPS/BN paths remain runnable. Set `NXUSKIT_COMMON_SENSE_FIXTURE_LLM=1` for deterministic smoke runs that keep LLM answers/facts fixture-backed while still invoking local CLIPS, BN, and Pro guardrail runtimes.

## What this demonstrates

**Difficulty: Advanced** ♦🏁 · LLM · CLIPS · Solver · BN · ZEN

- **Summary:** Progressive LLM guardrails with CE CLIPS, selected BN risk scoring, and optional Pro Solver/ZEN repair feedback.
- **Scenario:** Refine LLM recommendations with structured extraction, selected guardrails, retry repair, and reevaluation.
- **`tech_tags` in manifest:** `LLM`, `CLIPS`, `Solver`, `BN`, `ZEN` - example id **`common-sense-guardrails`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Live LLM calls use an installed nxusKit SDK, and live local guardrails use `nxuskit-cli`. Mock mode uses only Python 3, Bash, and `jq`.
- **Languages in this example:** python, bash.
- **Models:** Live and auto mode can use `NXUSKIT_PROVIDER` with `NXUSKIT_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, reachable `OLLAMA_HOST`, or reachable `LMSTUDIO_BASE_URL`.
- **CLIPS:** Community validation is represented by scenario-local CLIPS rule files and normalized findings.
- **BN:** Community Bayesian Network inference uses scenario-local JSON network fixtures and `nxuskit-cli bn infer` in live/fixture-LLM runtime mode.
- **Pro:** Solver/Z3 and ZEN guardrails require nxusKit Pro for live execution. Mock mode simulates their finding shape without invoking the runtime.

## Scenario Purposes

| Scenario | Failure class | Guardrail fit |
|----------|---------------|---------------|
| `car-wash` | Implicit object-presence precondition | CLIPS explains the missing object precondition; Solver/Z3 can prove object-presence feasibility. BN is intentionally not modeled. |
| `coupon-stack` | Promotion policy and margin violation | CLIPS and ZEN handle crisp eligibility; BN adds probabilistic promotion risk and review priority. |
| `pallet-door` | Dimensional feasibility and unsafe geometry | CLIPS catches the rule and Solver/Z3 proves geometry. BN is intentionally not modeled. |
| `cold-chain` | Handling and auditability violation | CLIPS and ZEN handle policy checks; BN combines carrier certification, refrigeration, temperature logging, and handoff evidence into review risk. |

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
python3 main.py --scenario car-wash --mode mock --guardrails auto --json

cd ../bash
bash main.sh --scenario car-wash --mode mock --guardrails auto --json
```

All launch scenarios:

```bash
for scenario in car-wash coupon-stack pallet-door cold-chain; do
  python3 main.py --scenario "$scenario" --mode mock --guardrails auto --json
done
```

## Mode Behavior

- `--mode live`: default. Requires a configured live provider and fails before scenario content is sent if preflight is unavailable.
- `--mode mock`: uses checked-in fixtures for LLM answers, structured facts, guardrail findings, repair packets, and corrected answers. It performs no provider, network, or entitlement preflight.
- `--mode auto`: uses live execution when provider preflight succeeds; otherwise it labels the run as fixture-backed mock mode.

For local guardrail runtime smoke without model variability, export `NXUSKIT_COMMON_SENSE_FIXTURE_LLM=1` and run `--mode live`. The runners use checked-in LLM answers and fact fixtures, then execute CLIPS and the selected BN, Solver/Z3, or ZEN guardrail through the installed CLI. This is useful for validating local runtime and Pro entitlement wiring; it is not a live LLM quality test.

## Guardrail Selection

- `--guardrails auto`: default. Uses CLIPS, adds BN for `coupon-stack` and `cold-chain`, and uses the scenario's Pro mechanism when available. In live mode, Pro unavailability downgrades with a warning.
- `--guardrails clips`: CE-only guardrail loop.
- `--guardrails bn`: Community Bayesian risk/confidence loop for `coupon-stack` and `cold-chain`.
- `--guardrails solver` or `--guardrails z3`: Pro-only feasibility loop for `car-wash` and `pallet-door`.
- `--guardrails zen`: Pro-only policy loop for `coupon-stack` and `cold-chain`.
- `--guardrails clips,bn`: combined Community rule and BN risk guardrails for the BN-enabled scenarios.
- `--guardrails clips,solver`, `--guardrails clips,zen`, or `--guardrails clips,zen,bn`: combined CE + Pro guardrails. If any selected mechanism fails, the prompt is repaired and the answer is retried.

BN is deliberately absent from `car-wash` and `pallet-door`. Those failures are crisp object-presence and geometric feasibility problems, so CLIPS and Solver/Z3 are the primary mechanisms unless future scenarios introduce measurement uncertainty, damage likelihood, or load-stability risk.

Each run retries up to `--max-repair-attempts 3` by default. Every attempt re-extracts facts and reruns the selected guardrails, because a repaired answer can fix one problem and introduce another.

Live structured fact extraction prefers pure JSON. If the model wraps a valid JSON object in prose, the runners extract it and mark the structured-facts stage as `warn`; if no valid JSON object is recoverable after retry, the structured-facts stage is marked `fail` and the run falls back to checked-in fact fixtures so later guardrail stages can still show their behavior.

Provider preflight order is explicit nxusKit provider/model environment, phase-specific model environment, nxusKit-recognized cloud credentials, reachable Ollama, then reachable LM Studio. Do not commit provider credentials or license tokens.

For local Ollama live runs, the Python runner honors `OLLAMA_HOST` and uses a short 5 second connect timeout with a 120 second read timeout because local model responses can be slower than cloud providers. The Python runner requests JSON response format for fact extraction when the installed SDK exposes it, but v1.0.x does not expose provider-level `thinking_mode` in Python. Use the Bash/CLI runner for the strict local proof path because it can pass both `thinking_mode` and `response_format` through `nxuskit-cli call`.

Live runs can use one provider/model for every phase or override phases independently:

```bash
export NXUSKIT_PROVIDER=ollama
export NXUSKIT_MODEL=qwen3.5:4b
export OLLAMA_HOST=http://127.0.0.1:11434
```

Phase-specific provider overrides are also supported with `NXUSKIT_COMMON_SENSE_BASELINE_PROVIDER`, `NXUSKIT_COMMON_SENSE_FACTS_PROVIDER`, and `NXUSKIT_COMMON_SENSE_REPAIR_PROVIDER`. See [OLLAMA_MODELS.md](./OLLAMA_MODELS.md) for local Ollama model notes from the repository walkthrough.

Strict live smoke is gated separately so mock fallback output is not mistaken for live provider output:

```bash
cd examples/integrations/common-sense-guardrails/bash
RUN_LIVE_SMOKE=1 ./strict_live_smoke.sh
```

Deterministic local runtime smoke for all scenarios:

```bash
export NXUSKIT_COMMON_SENSE_FIXTURE_LLM=1

for scenario in car-wash coupon-stack pallet-door cold-chain; do
  python3 main.py --scenario "$scenario" --mode live --guardrails auto --json
done

cd ../bash
for scenario in car-wash coupon-stack pallet-door cold-chain; do
  bash main.sh --scenario "$scenario" --mode live --guardrails auto --json
done
```

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
mock-corrected-facts.json
mock-repair.json
mock-corrected.json
```

Pro-enabled scenarios add one of:

```text
solver-problem.json
decision-model.json
```

BN-enabled scenarios add:

```text
bn-network.json
bn-guardrail.json
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

Guardrail findings normalize to `mechanism`, `tier`, `status`, `rule_id`, `severity`, `message`, `evidence`, and `repair_hint`. BN findings use `mechanism: "bn"` and include posterior evidence for `needs_review`. Expected-output fixtures list required stage ids, expected finding rule ids, correction text fragments, and optional Pro or BN stage metadata.

## Adding a Scenario

1. Create `scenarios/<name>/`.
2. Add every required Community file listed above.
3. Include a stable `id`, non-empty prompts, and a `repair_template` containing `{findings}` in `problem.json`.
4. Add scenario-local `rules.clp` findings with stable kebab-case rule ids.
5. Add `solver-problem.json` or `decision-model.json` only when the optional Pro stage is meaningful.
6. Add `bn-network.json` and `bn-guardrail.json` only when uncertainty, noisy evidence, or risk scoring is meaningful.
7. Run validation and both contract test suites before updating manifest scenarios.

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
