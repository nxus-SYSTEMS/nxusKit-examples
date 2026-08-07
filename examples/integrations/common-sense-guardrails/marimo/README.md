# Interactive Reasoning Lab

This ordinary-Python Marimo frontend renders canonical records from the
existing common-sense-guardrails core. It starts in offline Fixture mode and
does not build a record until the user submits **Analyze**. The compact control
surface keeps all providers and Reasoning Engines visible while distinguishing
availability from scenario applicability.

## Setup

Use Python 3.11 or later and the pinned lock from this directory. The
`nxuskit-py==1.0.5` dependency must come from the released v1.0.5 package with
the matching released native v1.0.5 bundle when a native runtime is selected.
The fixture workflows below do not require a provider, credential, entitlement,
or native invocation.

```bash
cd examples/integrations/common-sense-guardrails/marimo
uv sync --frozen
uv run marimo run reasoning_lab.py
```

For a local browser session, bind only to loopback:

```bash
uv run marimo run reasoning_lab.py --host 127.0.0.1 --port 2718
```

| Mode | `coupon-stack` with nxusKit v1.0.5 | Other scenarios |
| --- | --- | --- |
| **Fixture** | Deterministic synthetic evidence. No provider is contacted. | Builds deterministic synthetic evidence without contacting a provider. |
| **Auto** | Uses checked-in fixtures because the Python provider path cannot preserve the required strict schema; no provider is contacted. | May try the selected compatible provider after Analyze and uses only a supported, explicitly labeled fallback. |
| **Live** | Unavailable: the Python provider path cannot preserve the required strict schema. | Runs the selected enabled provider and model after Analyze. |

Only Coupon stack Live is contained. Providers remain visible with truthful
global availability, but the UI marks them not applicable to Coupon stack and
does not require or contact one for Coupon Auto. Other scenarios retain their
supported mode behavior. Strict Coupon stack Live can return only after an
independently accepted released-v2 Python provider-parity result and exact
Examples compatibility proof; version `2.0.0` alone does not enable it.

Changing Scenario, Mode, Provider, Model, Reasoning Engines, or maximum repair
attempts does not run inference or a Reasoning Engine. Model catalog discovery
is the only reactive provider-related operation, and it is bounded, read-only,
and performed through released nxusKit.

The result pairs a concise summary with Altair evidence charts and searchable
Polars tables. Facts, findings, evidence, attempts, mechanisms, bounded claims
scale profiles, and raw canonical JSON remain inspectable without creating a
second reasoning authority.

## Run Activity, LLM Interactions, and session export

After Analyze, **Run Activity** reports safe, ordered UTC events from the
existing provider, fact-extraction, Reasoning Engine, repair, and completion
boundaries. Its synchronized **LLM Interactions** pane makes the corresponding
application-visible **System Prompt**, **User Prompt**, provider-visible
response, repair instructions, prompt delta, and evaluated engine outcome
inspectable as plain text. Fixture cards remain explicit that no provider was
contacted. Auto records a stopped Live attempt and its Fixture fallback as
separate interactions when both occur. These views observe the canonical run;
they do not add another provider or reasoning execution path and never display
credential values or raw license claims.

A requested card appears when an LLM call begins. Its response becomes visible
when that non-streaming call completes; the example does not imply token-level
streaming. Fact-extraction calls use quieter styling but remain visible and
linked to their Run Activity events. Selecting or scrolling a linked item
centers its semantic counterpart rather than matching raw scroll percentages.
Unlinked activity remains visible with a neutral **No LLM call** label.

Live auto-follow starts on every Analyze. Manual scrolling away from the live
edge pauses it, and returning to the bottom automatically resumes it. A subtle
down-arrow also jumps to the newest linked pair and reports unseen interaction
updates, but clicking it is not required to resume. Arrow Up and Arrow Down
move among linked calls only while focus is inside the split surface; no global
keyboard shortcut is installed.

On desktop, the LLM pane has **Normal, Expanded, and Collapsed** states. Expanded
keeps a compact Run Activity timeline beside a wider interaction pane. On
narrow screens, only **Expanded and Collapsed** are used so one full-width pane
is visible at a time. The separator control reports its state and is keyboard
operable.

**Maximum repair attempts** means additional repaired responses after one
initial response. Response attempts are one-based: response attempt 1 is the
initial response, and repair attempt 1 produces response attempt 2. A maximum
of three repairs therefore permits at most four responses. The loop stops
early when a response is accepted and never creates repair instructions unless
the corresponding next response will run.

Fact extraction completion is a neutral processing result, not guardrail
acceptance. **Accepted** means every applied Reasoning Engine accepted the
response and it may proceed downstream. **Rejected** means fact extraction or
at least one applied engine blocked the response from downstream use. Run
activity names each engine decision, response attempt, repair attempt, and
blocking-finding count.

The active timer displays `hh:mm:ss`, updates once per second, and truncates to
whole seconds. Completed/stopped status and Summary Elapsed use the same
authoritative millisecond receipt in `hh:mm:ss.ccc` format. Analyze remains
disabled during synchronous execution. Cancel is intentionally unavailable
until the execution boundary can safely cancel provider and native work rather
than merely stop waiting for it.

**Export JSON** downloads one human-readable file with kind
`nxuskit.reasoning-lab-session`. The ordinary, transcript-free export uses
schema version `1.0.0`. Before a run, it is a settings-only export with
`results: null`. After a run, unchanged controls export the submitted settings
and corresponding safe results. If the controls have become a draft that
differs from those results, the UI explains the mismatch and offers exactly two
choices:

- **Original settings + results** (default)
- **Draft settings only**

For an original settings-and-results export, **Include Full LLM Transcript** is
unchecked by default. Selecting it creates schema version `2.0.0` and adds the
same complete application prompts and provider-visible responses shown in the
LLM Interactions pane, plus their event links, repair context, and outcomes.
Draft settings-only exports and default exports remain transcript-free. The
canonical Raw JSON reasoning record is unchanged and never gains transcript
content.

Import is not yet implemented. A future import can therefore evolve against a
stable, versioned document without making the current UI imply that loading or
rerunning an exported session is already supported.

## Availability and execution boundary

All supported providers are visible. Claude, OpenAI, Groq, and xAI remain
disabled until their corresponding credential **name** is detected; no value is
shown, serialized, persisted, hashed, or returned. Ollama and LM Studio model
catalogs are checked asynchronously at startup through released nxusKit.
Selecting a cloud provider starts the same bounded SDK discovery only when its
in-memory catalog is absent or stale. Opening the Model selector does not start
discovery. **Refresh models** explicitly refreshes only the selected provider.
Discovery never performs inference, pulls a model, starts or stops a provider,
or changes a provider cache or configuration.

The Model selector displays only fields reported by released nxusKit:
description, capabilities, context window, and locality. Missing fields,
including model size when the SDK does not report it, display as **not
reported** rather than being inferred from a model identifier.

All five Reasoning Engines remain visible. Community CLIPS, Bayesian inference,
and the synthetic Claims Audit are available without a Pro entitlement.
Solver/Z3 and ZEN remain disabled unless released v1.0.5 validates the exact
feature grant; token presence alone never enables Pro. An enabled engine that
does not apply to the current Scenario remains selectable and is shown in
italics. Selections persist across Scenario changes. Analyze applies only the
enabled, applicable subset and reports unavailable or unsupported selections as
skipped instead of rejecting the request.

Fixture is the default. Auto and Live selections are explicit, and Live runs
fail before execution if the submitted provider or model is unavailable. The UI
does not invoke cloud providers, local models, CLIPS, BN, Solver/Z3, or ZEN
until an explicit submitted request reaches the existing canonical runner.

`NXUSKIT_COMMON_SENSE_FIXTURE_LLM=1` is a deterministic smoke-test override,
not an interactive run mode. When it is present, the UI disables provider-backed
Auto and Live choices and explains that those modes are unavailable. Contained
Coupon stack Auto remains available because it is explicitly fixture-backed and
never contacts a provider. Normal interactive launches should omit the override.
This prevents a checked-in LLM answer plus live local Reasoning Engine smoke
from being mistaken for a real provider execution.

## Offline Community paths

- **cold-chain**: uses the existing synthetic cold-chain fixture and selected
  Community CLIPS/BN record path.
- **synthetic-claims-audit**: uses the tiny checked-in synthetic administrative
  data-quality and evidence-completeness fixture. Its output is an
  expert-review record, not an operational determination. The Summary labels
  this scenario as an offline synthetic audit even if a provider is selected;
  it does not claim provider contact.

The front end is intentionally fixture-first. Its script form shows the gate
without running anything:

```bash
uv run python frontend_core.py --json
uv run python frontend_core.py --json --analyze --scenario cold-chain
uv run python frontend_core.py --json --analyze --scenario synthetic-claims-audit
```

## Optional Pro selection

Solver and ZEN remain visible but disabled until a validated v1.0.5 feature
grant is available. Fixture mode remains completely offline; when a granted Pro
engine is selected, its fixture evidence remains explicitly non-runtime. Actual
Pro execution requires an explicit submitted Live or otherwise supported
runtime path through the canonical released nxusKit CLI/native bundle.

## Bounded synthetic scale proof

The adjacent Python helpers accept only seeded `1k`, `100k`, or `1m` temporary
expansion profiles. They create local generated rows after an explicit command,
then demonstrate a Polars lazy scan, synthetic reference join, aggregation,
and streaming collection. The lab shows the bounded profile choices and
claims exception categories without reactively generating data. Generated
output is not committed.

## Container reproduction

The Dockerfile is for local reproduction only. Build from the repository root
so it can read the existing offline fixtures:

```bash
docker build -f examples/integrations/common-sense-guardrails/marimo/Dockerfile -t nxuskit-reasoning-lab:local .
docker run --rm -p 2718:2718 nxuskit-reasoning-lab:local
```

Do not publish the image, expose it as a hosted service, or add real or
customer data. This example contains only synthetic local fixtures.
