# Model Research Workbench

This Marimo/Polars workbench is an interactive view over the existing Model
Research Harness. It starts with no evaluation: changing a control does not
call a provider, local adapter, engine, external command, or report writer.
Press **Run Evaluation** to send one explicit request to the canonical harness.

## Local setup

Use Python 3.11 or later and this directory's locked dependencies. The app is
bound to the released `nxuskit-py==1.0.5` package. A native path, when selected
by an existing harness config, must use the matching released v1.0.5 native
bundle; the fixture and mock paths below do not invoke it.

```bash
cd examples/integrations/model-research-harness/marimo
uv sync --frozen
uv run --frozen marimo run research_workbench.py \
  --host 127.0.0.1 --port 2719 --headless
```

Open <http://127.0.0.1:2719> in a local browser. The initial view shows all
built-in configurations with descriptions and test counts, provider/model
availability, evaluation-capability use, and the single submission boundary.

## What you can inspect

- Built-in harness configurations, including lifecycle-sensitive entries that
  remain visible and disabled. These are version-controlled example resources,
  not user-saved configurations.
- **Fixture** (`mock`) uses deterministic synthetic responses and does not call
  a provider. **Live** requires an available provider and explicit model.
  **Auto** may use an explicitly selected compatible provider/model and
  otherwise follows only the fallback supported by the chosen configuration.
  Policy Dry Run and Promptfoo Import remain separately labeled modes.
- Empty `include_tests` and `exclude_tests` fields run every test configured in
  the selected built-in configuration. Comma-separated IDs select a subset or
  remove matching tests.
- Evaluation-capability rows distinguish **Used by This Configuration** from
  **Available, Not Used** and unavailable capabilities. Availability alone does
  not execute or add a capability to a run.
- **Run Activity** shows configuration, filtering, provider request/response,
  parsing, assertions, policy, Bayesian aggregation, and report assembly as
  they occur. **Model Interactions** shows linked full prompts, responses,
  parsed output, assertion diagnostics, policy results, and truthful Fixture or
  Live provenance. Select a linked event, use the arrow keys to navigate, or
  use the pane controls to collapse/expand details and jump back to live output.
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

External-adapter configurations require the contextual **Allow External
Adapter** acknowledgement before **Run Evaluation** is enabled. It permits only
the selected configuration's existing explicit adapter path; it does not allow
lifecycle mutation, which remains unavailable from this frontend in every
mode. **Write Reports** is off by default. When explicitly selected, output is
confined to a new run-specific directory below this example's ignored
`.tmp/model-research-workbench/` path; it does not publish or upload anything.

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
