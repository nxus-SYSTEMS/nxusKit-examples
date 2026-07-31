"""Fixture-first interactive frontend for the canonical Reasoning Lab record."""

import marimo

__generated_with = "0.23.15"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    import os

    import marimo as mo

    from availability import (
        inspect_mechanism_availability,
        inspect_provider_availability,
    )
    from frontend_core import SCENARIOS, analyze_request
    from presenters import chart_specs, record_tables

    return (
        SCENARIOS,
        analyze_request,
        chart_specs,
        inspect_mechanism_availability,
        inspect_provider_availability,
        json,
        mo,
        os,
        record_tables,
    )


@app.cell
def _(SCENARIOS, mo):
    scenario = mo.ui.dropdown(
        options=list(SCENARIOS), value="cold-chain", label="Scenario"
    )
    run_mode = mo.ui.dropdown(
        options=["fixture", "auto", "live"], value="fixture", label="Run mode"
    )
    return run_mode, scenario


@app.cell
def _(
    inspect_mechanism_availability,
    inspect_provider_availability,
    mo,
    os,
    run_mode,
    scenario,
):
    provider_availability = inspect_provider_availability(os.environ)
    mechanism_availability = inspect_mechanism_availability(scenario.value)

    enabled_providers = [
        entry["id"] for entry in provider_availability if entry["enabled"]
    ]
    unavailable_providers = [
        f"{entry['id']}: {entry['reason']}"
        for entry in provider_availability
        if not entry["enabled"]
    ]
    provider = mo.ui.dropdown(
        options=enabled_providers,
        value=None,
        allow_select_none=True,
        label="Provider",
        disabled=not enabled_providers,
    )
    model = mo.ui.text(value="", label="Model", disabled=not enabled_providers)
    unavailable_provider_list = mo.ui.multiselect(
        options=unavailable_providers,
        label="Unavailable providers (visible, disabled)",
        disabled=True,
    )

    enabled_mechanisms = [
        entry["id"] for entry in mechanism_availability if entry["enabled"]
    ]
    unavailable_mechanisms = [
        f"{entry['id']}: {entry['reason']}"
        for entry in mechanism_availability
        if not entry["enabled"]
    ]
    defaults = [item for item in ("clips", "bn") if item in enabled_mechanisms]
    mechanisms = mo.ui.multiselect(
        options=enabled_mechanisms,
        value=defaults or enabled_mechanisms[:1],
        label="Mechanisms",
        disabled=not enabled_mechanisms,
    )
    unavailable_mechanism_list = mo.ui.multiselect(
        options=unavailable_mechanisms,
        label="Unavailable mechanisms (visible, disabled)",
        disabled=True,
    )
    repair_attempts = mo.ui.number(
        start=1, stop=10, step=1, value=3, label="Repair attempts"
    )
    configuration = mo.ui.dictionary(
        {
            "scenario": scenario,
            "mode": run_mode,
            "provider": provider,
            "model": model,
            "mechanisms": mechanisms,
            "max_repair_attempts": repair_attempts,
        },
        label="Configure",
    )
    request_form = mo.ui.form(
        configuration,
        submit_button_label="Analyze",
        label="Configure the synthetic reasoning record",
    )
    mo.vstack(
        [
            mo.md(
                "# nxusKit Reasoning Lab\n"
                "Fixture-first Community analysis. Configuration changes do not run a "
                "provider, engine, adapter, or filesystem operation."
            ),
            request_form,
            unavailable_provider_list,
            unavailable_mechanism_list,
        ]
    )
    return (
        mechanism_availability,
        provider_availability,
        request_form,
    )


@app.cell
def _(analyze_request, mechanism_availability, provider_availability, request_form):
    submitted_request = request_form.value
    if submitted_request is None:
        response = analyze_request(
            {
                "scenario": "cold-chain",
                "mode": "fixture",
                "provider": None,
                "model": None,
                "mechanisms": ["clips", "bn"],
                "max_repair_attempts": 3,
            },
            submitted=False,
            provider_availability=provider_availability,
            mechanism_availability=mechanism_availability,
        )
    else:
        response = analyze_request(
            submitted_request,
            submitted=True,
            provider_availability=provider_availability,
            mechanism_availability=mechanism_availability,
        )
    return (response,)


@app.cell
def _(chart_specs, json, mo, record_tables, response):
    record = response["record"]
    if record is None:
        result_view = mo.callout(
            "Select inputs, then press Analyze. No reasoning record has been built.",
            kind="info",
        )
    else:
        provenance = record["provenance"]
        final = record["final"]
        submitted = response["mode"]
        summary = mo.md(
            "## Summary\n"
            f"**Scenario:** {record['scenario']['label']}  \\n"
            f"**Requested / resolved mode:** {submitted} / {provenance['mode']}  \\n"
            f"**Provider / model:** {response['requested_provider'] or 'not selected'} / "
            f"{response['requested_model'] or 'not selected'}  \\n"
            f"**nxusKit Python / native:** {provenance['sdk_python_version']} / "
            f"{provenance['sdk_native_version']}  \\n"
            f"**Synthetic data:** {record['scenario']['synthetic']}  \\n"
            f"**Review disposition:** {final['review_disposition']}  \\n"
            "**Mechanism execution:** "
            + ", ".join(
                f"{item['id']} ({item['tier']}, {item['availability']}, "
                f"runtime_executed={item['runtime_executed']})"
                for item in record["mechanisms"]
            )
            + "  \\n"
            f"{final['summary']}"
        )
        charts = chart_specs(record)
        visual_evidence = mo.vstack(
            [
                mo.md("## Visual Evidence"),
                *[
                    mo.ui.altair_chart(chart, label=name.replace("_", " ").title())
                    for name, chart in charts.items()
                ],
            ]
        )
        tables = record_tables(record)
        evidence_tabs = mo.tabs(
            {
                "Findings": mo.ui.table(tables["findings"], label="Findings"),
                "Evidence": mo.ui.table(tables["evidence"], label="Evidence"),
                "Attempts": mo.ui.table(tables["attempts"], label="Attempts"),
                "Facts": mo.ui.table(tables["facts"], label="Facts"),
                "Mechanisms": mo.ui.table(tables["mechanisms"], label="Mechanisms"),
                "Claims scale": mo.ui.table(
                    tables["claims_scale_profiles"], label="Claims scale profiles"
                ),
            }
        )
        result_view = mo.vstack(
            [
                mo.hstack([summary, visual_evidence], wrap=True, widths="equal"),
                mo.md("## Inspect evidence"),
                evidence_tabs,
                mo.accordion(
                    {
                        "Raw JSON": mo.md(
                            f"```json\\n{json.dumps(record, indent=2, sort_keys=True)}\\n```"
                        )
                    }
                ),
            ]
        )
    result_view


if __name__ == "__main__":
    app.run()
