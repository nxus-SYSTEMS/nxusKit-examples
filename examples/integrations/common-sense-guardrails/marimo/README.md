# Fixture-First Reasoning Lab

This ordinary-Python Marimo frontend renders canonical records from the
existing common-sense-guardrails core. It starts in offline fixture mode and
does not build a record until the user selects **Analyze**.

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

Solver and ZEN are never selected by default. If explicitly selected in this
frontend, fixture mode reports them as unavailable and continues with the
available Community mechanisms; it does not simulate a Pro invocation. Use the
canonical CLI example only when an installed released v1.0.5 bundle and the
appropriate tier are available.

## Bounded synthetic scale proof

The adjacent Python helpers accept only seeded `1k`, `100k`, or `1m` temporary
expansion profiles. They create local generated rows, then demonstrate a
Polars lazy scan, synthetic reference join, aggregation, and streaming
collection. Generated output is not committed. See Spec 012 evidence for the
machine-specific local observations.

## Container reproduction

The Dockerfile is for local reproduction only. Build from the repository root
so it can read the existing offline fixtures:

```bash
docker build -f examples/integrations/common-sense-guardrails/marimo/Dockerfile -t nxuskit-reasoning-lab:local .
docker run --rm -p 2718:2718 nxuskit-reasoning-lab:local
```

Do not publish the image, expose it as a hosted service, or add real or
customer data. This example contains only synthetic local fixtures.
