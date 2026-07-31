# Interactive Reasoning Lab

This ordinary-Python Marimo frontend renders canonical records from the
existing common-sense-guardrails core. It starts in offline fixture mode and
does not build a record until the user submits **Analyze**. Configure a
scenario, mode, provider/model, compatible mechanisms, and one through ten
repair attempts; changing those controls alone runs no provider, engine,
adapter, or filesystem operation.

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

The result pairs a concise summary with Altair evidence charts and searchable
Polars tables. Facts, findings, evidence, attempts, mechanisms, bounded claims
scale profiles, and raw canonical JSON remain inspectable without creating a
second reasoning authority.

## Availability and execution boundary

All supported providers are visible. Claude, OpenAI, Groq, and xAI remain
disabled until their corresponding credential **name** is detected; no value is
read, shown, validated, or stored. Ollama and LM Studio remain disabled unless
an explicit bounded local preflight is added later; the app does not start a
service or download a model. Solver/Z3 and ZEN remain visible and disabled
unless the released v1.0.5 license path validates the exact feature grant.
Token presence alone never enables Pro.

Fixture is the default. Auto and live selections are explicit, and live runs
fail before execution if a selected provider or mechanism is disabled. The UI
does not invoke cloud providers, local models, CLIPS, BN, Solver/Z3, or ZEN
until an explicit submitted request reaches the existing canonical runner.

## Offline Community paths

- **cold-chain**: uses the existing synthetic cold-chain fixture and selected
  Community CLIPS/BN record path.
- **synthetic-claims-audit**: uses the tiny checked-in synthetic administrative
  data-quality and evidence-completeness fixture. Its output is an
  expert-review record, not an operational determination.

The front end is intentionally fixture-first. Its script form shows the gate
without running anything:

```bash
uv run python frontend_core.py --json
uv run python frontend_core.py --json --analyze --scenario cold-chain
uv run python frontend_core.py --json --analyze --scenario synthetic-claims-audit
```

## Optional Pro selection

Solver and ZEN are never selected by default. They remain visible but disabled
until a validated v1.0.5 feature grant is available; fixture mode remains a
complete Community result and does not simulate a Pro invocation. Use the
canonical CLI example only when an installed released v1.0.5 bundle and the
appropriate tier are available.

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
