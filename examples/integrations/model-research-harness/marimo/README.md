# Model Research Workbench

This Marimo/Polars workbench is a fixture-first view over the existing Model
Research Harness. It starts with no evaluation: changing a control does not
call a provider, local adapter, engine, external command, or report writer.
Press **Run evaluation** to send one explicit request to the canonical harness.

## Local setup

Use Python 3.11 or later and this directory's locked dependencies. The app is
bound to the released `nxuskit-py==1.0.5` package. A native path, when selected
by an existing harness config, must use the matching released v1.0.5 native
bundle; the fixture and mock paths below do not invoke it.

```bash
cd examples/integrations/model-research-harness/marimo
uv sync --frozen
uv run marimo run research_workbench.py --host 127.0.0.1 --port 2719
```

Open <http://127.0.0.1:2719> in a local browser. The initial view shows all
checked-in configurations, availability and tier truth, a disabled provider
and model control when no eligible provider is detected, and the single
submission boundary.

## What you can inspect

- Checked-in harness configurations, including lifecycle-sensitive entries
  that remain visible and disabled.
- Mock, auto, live, dry-run-policy, and Promptfoo-import modes. The default is
  `mock`; availability never turns a selection into a run.
- Altair charts and Polars result, confidence, capability-truth, policy, and
  failure tables after explicit submission. Latency, token, and cost measures
  are absent unless the canonical report actually supplies them.
- A safe JSON evidence projection that omits raw output, prompts, messages, and
  raw responses.

## Availability and effect boundaries

Claude, OpenAI, Groq, and xAI are shown but disabled until their corresponding
credential **name** is detected. The frontend never reads, displays, validates,
or retains credential values. Ollama and LM Studio remain disabled unless a
separate bounded local endpoint preflight is supplied; the workbench never
starts a service or downloads a model. CLIPS/BN advertise fixture fallback when
native execution is not explicitly proven. Solver and ZEN remain disabled
unless the released v1.0.5 license path validates the exact feature grant.

External-adapter configs require an explicit submitted acknowledgement.
Lifecycle mutation is unavailable from this frontend in every mode. Report
writing is off by default and, if selected, is confined to this example's
ignored `.tmp/model-research-workbench/` directory.

## Local container reproduction

The Docker recipe is optional and only for local reproduction. Build from the
repository root, then bind the host port to loopback only:

```bash
docker build -f examples/integrations/model-research-harness/marimo/Dockerfile \
  -t nxuskit-model-research-workbench:local .
docker run --rm -p 127.0.0.1:2719:2719 nxuskit-model-research-workbench:local
```

Do not publish the image, expose the app as a hosted service, or supply
customer, production, personal, or real-person data. The workbench is a local,
synthetic-fixture example.
