import marimo

__generated_with = "0.23.15"
app = marimo.App(width="full")


@app.cell
def _():
    import json

    import marimo as mo

    from frontend_core import run_evaluation
    from presenters import report_charts, report_tables
    from workbench_contract import (
        availability_markdown,
        normalise_filters,
        safe_report_json,
        workbench_controls,
    )

    return (
        availability_markdown,
        json,
        mo,
        normalise_filters,
        report_charts,
        report_tables,
        run_evaluation,
        safe_report_json,
        workbench_controls,
    )


@app.cell
def _(workbench_controls):
    controls = workbench_controls()
    provider_availability = list(controls["providers"].values())
    return controls, provider_availability


@app.cell
def _(availability_markdown, controls, mo):
    config_entries = controls["configs"]
    enabled_config_ids = [
        config_id for config_id, item in config_entries.items() if item["enabled"]
    ]
    disabled_configs = [
        f"{config_id}: {item['reason']}"
        for config_id, item in config_entries.items()
        if not item["enabled"]
    ]
    provider_entries = controls["providers"]
    enabled_providers = [
        provider_id for provider_id, item in provider_entries.items() if item["enabled"]
    ]
    unavailable_providers = [
        f"{provider_id}: {item['reason']}"
        for provider_id, item in provider_entries.items()
        if not item["enabled"]
    ]
    engine_truth = [
        f"{engine_id}: {item['tier']} / {item['status']} / {item['reason']}"
        for engine_id, item in controls["engines"].items()
    ]

    config_id = mo.ui.dropdown(
        options=enabled_config_ids,
        value="nxuskit-harness-basic.yaml",
        label="Checked-in config",
    )
    mode = mo.ui.dropdown(options=controls["modes"], value="mock", label="Mode")
    provider = mo.ui.dropdown(
        options=enabled_providers,
        value=None,
        allow_select_none=True,
        label="Provider",
        disabled=not enabled_providers,
    )
    model = mo.ui.text(value="", label="Model", disabled=not enabled_providers)
    include_tests = mo.ui.text(value="", label="Include test IDs (comma-separated)")
    exclude_tests = mo.ui.text(value="", label="Exclude test IDs (comma-separated)")
    allow_external = mo.ui.checkbox(
        label="I explicitly acknowledge the external-adapter trust gate", value=False
    )
    write_reports = mo.ui.checkbox(
        label="Write bounded local reports after submission", value=False
    )
    configuration = mo.ui.dictionary(
        {
            "config_id": config_id,
            "mode": mode,
            "provider": provider,
            "model": model,
            "include_tests": include_tests,
            "exclude_tests": exclude_tests,
            "allow_external": allow_external,
            "write_reports": write_reports,
        },
        label="Configure",
    )
    request_form = mo.ui.form(
        configuration,
        submit_button_label="Run evaluation",
        label="Configure the fixture-first workbench",
    )
    mo.vstack(
        [
            mo.md(
                "# nxusKit Model Research Workbench\n"
                "Community fixture/mock evaluation by default. Changing controls does "
                "not call a provider, adapter, engine, or filesystem writer."
            ),
            request_form,
            mo.md(availability_markdown(controls)),
            mo.ui.multiselect(
                options=disabled_configs,
                label="Unavailable configs (visible, disabled)",
                disabled=True,
            ),
            mo.ui.multiselect(
                options=unavailable_providers,
                label="Unavailable providers (visible, disabled)",
                disabled=True,
            ),
            mo.ui.multiselect(
                options=engine_truth,
                label="Engine tier and execution truth",
                disabled=True,
            ),
        ]
    )
    return (request_form,)


@app.cell
def _(normalise_filters, provider_availability, request_form, run_evaluation):
    submitted_request = request_form.value
    if submitted_request is None:
        response = run_evaluation(
            {
                "config_id": "nxuskit-harness-basic.yaml",
                "mode": "mock",
                "provider": None,
                "model": None,
                "include_tests": [],
                "exclude_tests": [],
                "allow_external": False,
                "write_reports": False,
            },
            submitted=False,
            provider_availability=provider_availability,
        )
    else:
        request = {
            **submitted_request,
            "include_tests": normalise_filters(submitted_request.get("include_tests")),
            "exclude_tests": normalise_filters(submitted_request.get("exclude_tests")),
        }
        try:
            response = run_evaluation(
                request,
                submitted=True,
                provider_availability=provider_availability,
            )
        except ValueError as exc:
            response = {"report": None, "message": str(exc), "report_path": None}
    return (response,)


@app.cell
def _(json, mo, report_charts, report_tables, response, safe_report_json):
    report = response["report"]
    if report is None:
        result_view = mo.callout(str(response["message"]), kind="info")
    else:
        tables = report_tables(report)
        charts = report_charts(report)
        summary = mo.md(
            "## Summary\n"
            f"**Config:** {report['config_id']}  \\n"
            f"**Final status:** {report['final_status']}  \\n"
            f"**Report writing:** {response['report_path'] or 'not requested'}  \\n"
            "Only submitted evaluation can execute the canonical harness."
        )
        visual_evidence = mo.vstack(
            [
                mo.md("## Visual Evidence"),
                *[
                    mo.ui.altair_chart(chart, label=name.replace("_", " ").title())
                    for name, chart in charts.items()
                ],
            ]
        )
        inspections = mo.tabs(
            {
                "Results": mo.ui.table(tables["results"], label="Results"),
                "Confidence": mo.ui.table(tables["confidence"], label="Confidence"),
                "Capability Truth": mo.ui.table(
                    tables["capabilities"], label="Capability Truth"
                ),
                "Policy": mo.ui.table(tables["policy"], label="Policy"),
                "Failures": mo.ui.table(tables["failures"], label="Failures"),
            }
        )
        result_view = mo.vstack(
            [
                mo.hstack([summary, visual_evidence], wrap=True, widths="equal"),
                mo.md("## Inspect evidence"),
                inspections,
                mo.accordion(
                    {
                        "Raw JSON": mo.md(
                            "```json\\n"
                            + json.dumps(
                                safe_report_json(report), indent=2, sort_keys=True
                            )
                            + "\\n```"
                        )
                    }
                ),
            ]
        )
    result_view


if __name__ == "__main__":
    app.run()
