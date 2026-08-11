import marimo

__generated_with = "0.23.15"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    import os

    import marimo as mo

    from availability import released_license_status
    from frontend_core import EvaluationSubmissionGate, run_evaluation
    from harness.providers import ProviderError
    from model_discovery import ProviderDiscoveryCoordinator
    from presenters import report_charts, report_tables
    from research_activity import ResearchActivity
    from workbench_contract import safe_report_json
    from workbench_controls import WorkbenchControls

    return (
        EvaluationSubmissionGate,
        ProviderError,
        ProviderDiscoveryCoordinator,
        ResearchActivity,
        WorkbenchControls,
        json,
        mo,
        os,
        released_license_status,
        report_charts,
        report_tables,
        run_evaluation,
        safe_report_json,
    )


@app.cell
def _(os, released_license_status):
    license_status = released_license_status(environ=os.environ)
    return (license_status,)


@app.cell
def _(
    ProviderDiscoveryCoordinator,
    ResearchActivity,
    WorkbenchControls,
    license_status,
    mo,
    os,
):
    discovery_coordinator = ProviderDiscoveryCoordinator()
    workbench_widget = WorkbenchControls(
        coordinator=discovery_coordinator,
        environ=os.environ,
        license_status=license_status,
    )
    activity_widget = ResearchActivity()
    controls = mo.ui.anywidget(workbench_widget)
    activity_view = mo.ui.anywidget(activity_widget)
    mo.vstack([mo.md("# nxusKit Model Research Workbench"), controls])
    return activity_view, activity_widget, controls, workbench_widget


@app.cell
def _(EvaluationSubmissionGate, run_evaluation):
    evaluation_gate = EvaluationSubmissionGate(evaluate=run_evaluation)
    return (evaluation_gate,)


@app.cell
def _(
    ProviderError,
    activity_widget,
    controls,
    evaluation_gate,
    run_evaluation,
    workbench_widget,
):
    control_state = controls.value
    provider_availability = list(control_state.get("providers", []))
    submit_generation = int(control_state.get("submit_generation", 0))
    submitted_request = dict(control_state.get("submitted_request", {}))
    draft_request = {
        "config_id": str(
            control_state.get("selected_config", "nxuskit-harness-basic.yaml")
        ),
        "mode": str(control_state.get("selected_mode", "mock")),
        "provider": control_state.get("selected_provider"),
        "model": control_state.get("selected_model"),
        "include_tests": [],
        "exclude_tests": [],
        "allow_external": bool(control_state.get("allow_external", False)),
        "write_reports": bool(control_state.get("write_reports", False)),
    }
    if submit_generation < 1 or not submitted_request:
        response = run_evaluation(
            draft_request,
            submitted=False,
            provider_availability=provider_availability,
        )
    else:
        activity_widget.begin_run(submit_generation)
        try:
            response = evaluation_gate.evaluate(
                submit_generation,
                submitted_request,
                provider_availability=provider_availability,
                event_sink=activity_widget.append_event,
                interaction_sink=activity_widget.append_interaction_update,
            )
            activity_widget.complete_run(
                response["report"] or {"final_status": "not-run"}
            )
            workbench_widget.completion_state = "completed"
        except (ValueError, ProviderError) as exc:
            safe_message = (
                "The provider evaluation stopped safely. Review the retained activity "
                "evidence, provider, and model before trying again."
                if isinstance(exc, ProviderError)
                else str(exc)
            )
            activity_widget.fail_run(safe_message)
            response = {
                "report": None,
                "message": safe_message,
                "report_path": None,
            }
            workbench_widget.completion_state = "failed"
        workbench_widget.completed_generation = submit_generation
    return (response,)


@app.cell
def _(
    activity_view,
    json,
    mo,
    report_charts,
    report_tables,
    response,
    safe_report_json,
):
    report = response["report"]
    if report is None:
        result_view = mo.vstack(
            [mo.callout(str(response["message"]), kind="info"), activity_view]
        )
    else:
        tables = report_tables(report)
        charts = report_charts(report)
        summary = mo.md(
            f"""## Summary

- **Configuration:** {report["config_id"]}
- **Final status:** {report["final_status"]}
- **Report writing:** {response["report_path"] or "not requested"}

Only an explicitly submitted evaluation can execute the canonical harness.
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
                activity_view,
                mo.md("## Inspect Evidence"),
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
