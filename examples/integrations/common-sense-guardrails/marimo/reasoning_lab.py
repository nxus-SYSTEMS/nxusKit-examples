import marimo

__generated_with = "0.23.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import marimo as mo

    from frontend_core import (
        COMMUNITY_GUARDRAILS,
        DEFAULT_GUARDRAILS,
        PRO_GUARDRAILS,
        SCENARIOS,
        analyze_request,
    )

    return (
        COMMUNITY_GUARDRAILS,
        DEFAULT_GUARDRAILS,
        PRO_GUARDRAILS,
        SCENARIOS,
        analyze_request,
        json,
        mo,
    )


@app.cell
def _(COMMUNITY_GUARDRAILS, DEFAULT_GUARDRAILS, PRO_GUARDRAILS, SCENARIOS, mo):
    scenario = mo.ui.dropdown(
        options=list(SCENARIOS), value="cold-chain", label="Fixture scenario"
    )
    guardrails = mo.ui.multiselect(
        options=list(COMMUNITY_GUARDRAILS + PRO_GUARDRAILS),
        value=list(DEFAULT_GUARDRAILS),
        label="Mechanisms (Pro requires explicit selection)",
    )
    analyze = mo.ui.run_button(label="Analyze")
    mo.vstack([scenario, guardrails, analyze])
    return analyze, guardrails, scenario


@app.cell
def _(analyze, analyze_request, guardrails, scenario):
    response = analyze_request(
        scenario=scenario.value,
        selected_guardrails=guardrails.value,
        analyze=analyze.value,
    )
    return (response,)


@app.cell
def _(json, mo, response):
    mo.md(f"```json\n{json.dumps(response, indent=2, sort_keys=True)}\n```")
    return


if __name__ == "__main__":
    app.run()
