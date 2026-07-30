FROM ghcr.io/astral-sh/uv:0.7.20 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /workspace
COPY . /workspace
RUN cd examples/integrations/common-sense-guardrails/marimo && uv sync --frozen --no-dev --no-install-project

ENV PATH="/workspace/examples/integrations/common-sense-guardrails/marimo/.venv/bin:${PATH}"
EXPOSE 2718
CMD ["marimo", "run", "examples/integrations/common-sense-guardrails/marimo/reasoning_lab.py", "--host", "0.0.0.0"]
