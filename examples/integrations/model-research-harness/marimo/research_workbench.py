import marimo

__generated_with = "0.23.15"
app = marimo.App(width="full")


@app.cell
def _():
    def mode_guidance() -> str:
        """Describe the submitted modes in the same vocabulary as the control."""

        return """**Mode guidance**

Changing controls has no effect. After explicit Run evaluation:

- Mock (Fixture) — deterministic synthetic evidence; it does not call a provider.
- Auto — may attempt a compatible enabled live provider, then falls back only where supported.
- Live — runs the selected enabled provider.
"""

    return (mode_guidance,)


@app.cell
def _():
    import json
    import os

    import marimo as mo

    from availability import released_license_status
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
        os,
        report_charts,
        report_tables,
        run_evaluation,
        safe_report_json,
        workbench_controls,
        released_license_status,
    )


@app.cell
def _(os, released_license_status, workbench_controls):
    license_status = released_license_status(environ=os.environ)
    controls = workbench_controls(license_status=license_status)
    provider_availability = list(controls["providers"].values())
    return controls, provider_availability


@app.cell
def _(availability_markdown, controls, mo, mode_guidance):
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
            mo.md(mode_guidance()),
            request_form,
            mo.md(availability_markdown(controls)),
            mo.ui.multiselect(
                options=disabled_configs,
                label="Unavailable config options — disabled (reason shown)",
                disabled=True,
            ),
            mo.ui.multiselect(
                options=unavailable_providers,
                label="Unavailable provider options — disabled (reason shown)",
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
            f"""## Summary

- **Config:** {report["config_id"]}
- **Final status:** {report["final_status"]}
- **Report writing:** {response["report_path"] or "not requested"}

Only submitted evaluation can execute the canonical harness.
"""
        )
        visual_evidence = mo.vstack(
            [
                mo.md("## Visual Evidence"),
                *[
                    mo.ui.altair_chart(
                        chart.properties(width="container").properties(height=260),
                        label=name.replace("_", " ").title(),
                    )
                    for name, chart in charts.items()
                ],
            ]
        )
        inspections = mo.ui.tabs(
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
                summary,
                mo.md("## Inspect evidence"),
                inspections,
                visual_evidence,
                mo.accordion(
                    {
                        "Raw JSON": mo.md(
                            f"""```json
{json.dumps(safe_report_json(report), indent=2, sort_keys=True)}
```"""
                        )
                    }
                ),
            ]
        )
    result_view


if __name__ == "__main__":
    app.run()
