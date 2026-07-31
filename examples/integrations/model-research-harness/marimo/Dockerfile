FROM ghcr.io/astral-sh/uv:0.7.20 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /workspace
COPY . /workspace
RUN cd examples/integrations/model-research-harness/marimo && uv sync --frozen --no-dev --no-install-project

ENV PATH="/workspace/examples/integrations/model-research-harness/marimo/.venv/bin:${PATH}"
EXPOSE 2719
CMD ["marimo", "run", "examples/integrations/model-research-harness/marimo/research_workbench.py", "--host", "0.0.0.0", "--port", "2719"]
