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
        inspect_provider_availability,
        inspect_reasoning_engine_availability,
        released_license_status,
    )
    from frontend_core import (
        AnalysisSubmissionGate,
        analyze_request,
        format_elapsed_duration,
    )
    from model_discovery import ProviderDiscoveryCoordinator
    from presenters import chart_specs, record_tables
    from reasoning_controls import ReasoningControls
    from run_activity import RunActivity

    return (
        AnalysisSubmissionGate,
        ProviderDiscoveryCoordinator,
        ReasoningControls,
        RunActivity,
        analyze_request,
        chart_specs,
        format_elapsed_duration,
        inspect_provider_availability,
        inspect_reasoning_engine_availability,
        json,
        mo,
        os,
        record_tables,
        released_license_status,
    )


@app.cell
def _(os, released_license_status):
    license_status = released_license_status(environ=os.environ)
    return (license_status,)


@app.cell
def _(
    ProviderDiscoveryCoordinator,
    ReasoningControls,
    RunActivity,
    inspect_reasoning_engine_availability,
    license_status,
    mo,
    os,
):
    engine_availability = inspect_reasoning_engine_availability(license_status)
    discovery_coordinator = ProviderDiscoveryCoordinator()
    reasoning_widget = ReasoningControls(
        coordinator=discovery_coordinator,
        environ=os.environ,
        engine_availability=engine_availability,
    )
    run_activity_widget = RunActivity()
    controls = mo.ui.anywidget(reasoning_widget)
    activity_view = mo.ui.anywidget(run_activity_widget)
    controls
    return (
        activity_view,
        controls,
        engine_availability,
        reasoning_widget,
        run_activity_widget,
    )


@app.cell
def _(AnalysisSubmissionGate, analyze_request):
    analysis_gate = AnalysisSubmissionGate(analyze=analyze_request)
    return (analysis_gate,)


@app.cell
def _(
    analysis_gate,
    analyze_request,
    controls,
    engine_availability,
    reasoning_widget,
    run_activity_widget,
):
    control_state = controls.value
    provider_availability = list(control_state.get("providers", []))
    submit_generation = int(control_state.get("submit_generation", 0))
    submitted_request = dict(control_state.get("submitted_request", {}))
    draft_configuration = {
        "scenario": str(control_state.get("scenario", "cold-chain")),
        "mode": str(control_state.get("mode", "fixture")),
        "provider": control_state.get("selected_provider"),
        "model": control_state.get("selected_model"),
        "mechanisms": list(control_state.get("selected_engines", ["clips", "bn"])),
        "max_repair_attempts": int(control_state.get("max_repair_attempts", 3)),
    }
    run_activity_widget.set_draft_configuration(draft_configuration)
    if submit_generation < 1 or not submitted_request:
        response = analyze_request(
            draft_configuration,
            submitted=False,
            provider_availability=provider_availability,
            mechanism_availability=engine_availability,
        )
    else:
        run_activity_widget.begin_run(
            submitted_request,
            generation=submit_generation,
        )
        try:
            response = analysis_gate.evaluate(
                submit_generation,
                submitted_request,
                provider_availability=provider_availability,
                mechanism_availability=engine_availability,
                event_sink=run_activity_widget.append_event,
                interaction_sink=run_activity_widget.append_interaction_update,
            )
        except Exception:
            run_activity_widget.fail_run(
                "Analysis stopped before a safe result was available."
            )
            reasoning_widget.completed_elapsed_ms = run_activity_widget.final_elapsed_ms
            reasoning_widget.completion_state = "failed"
            reasoning_widget.completed_generation = submit_generation
            raise
        run_activity_widget.complete_run(response)
        reasoning_widget.completed_elapsed_ms = int(
            response["run_receipt"]["elapsed_ms"]
        )
        reasoning_widget.completion_state = (
            "completed" if response.get("record") is not None else "failed"
        )
        reasoning_widget.completed_generation = submit_generation
    return (response,)


@app.cell
def _(
    activity_view,
    chart_specs,
    format_elapsed_duration,
    json,
    mo,
    record_tables,
    response,
):
    record = response["record"]
    if record is None:
        result_view = mo.vstack(
            [
                mo.callout(
                    response.get(
                        "message",
                        "Choose the configuration above, then press Analyze. No reasoning record has been built.",
                    ),
                    kind="danger" if response.get("run_receipt") else "info",
                ),
                activity_view,
            ]
        )
    else:
        provenance = record["provenance"]
        final = record["final"]
        submitted = response["mode"]
        skipped = response.get("skipped_mechanisms", [])
        execution = response["execution"]
        run_receipt = response["run_receipt"]
        skipped_summary = (
            ", ".join(f"{item['id']} ({item['reason']})" for item in skipped)
            if skipped
            else "none"
        )
        summary = mo.md(
            f"""## Summary

- **Scenario:** {record["scenario"]["label"]}
- **Requested / resolved mode:** {submitted} / {provenance["mode"]}
- **Provider / model:** {response["requested_provider"] or "not selected"} / {response["requested_model"] or "not selected"}
- **LLM execution source:** {execution["llm_source"]} (provider contacted: {execution["provider_contacted"]})
- **Execution detail:** {execution["message"]}
- **Run started / completed (UTC):** {run_receipt["started_at_utc"]} / {run_receipt["completed_at_utc"]}
- **Elapsed:** {format_elapsed_duration(run_receipt["elapsed_ms"])}
- **nxusKit Python / native:** {provenance["sdk_python_version"]} / {provenance["sdk_native_version"]}
- **Synthetic data:** {record["scenario"]["synthetic"]}
- **Review disposition:** {final["review_disposition"]}
- **Reasoning Engine execution:** {", ".join(f"{item['id']} ({item['tier']}, {item['availability']}, runtime_executed={item['runtime_executed']})" for item in record["mechanisms"])}
- **Skipped Reasoning Engines:** {skipped_summary}

{final["summary"]}
"""
        )
        charts = chart_specs(record)
        chart_views = [
            mo.style(
                mo.ui.altair_chart(
                    chart.properties(width="container").properties(height=260),
                    chart_selection=False,
                    legend_selection=False,
                    label=name.replace("_", " ").title(),
                ),
                width="100%",
                min_width="18rem",
            )
            for name, chart in charts.items()
        ]
        visual_evidence = mo.vstack(
            [
                mo.md("## Visual Evidence"),
                mo.hstack(
                    chart_views,
                    align="stretch",
                    wrap=True,
                    widths="equal",
                ),
            ]
        )
        tables = record_tables(record)
        evidence_tabs = mo.ui.tabs(
            {
                "Findings": mo.ui.table(tables["findings"], label="Findings"),
                "Evidence": mo.ui.table(tables["evidence"], label="Evidence"),
                "Attempts": mo.ui.table(tables["attempts"], label="Attempts"),
                "Facts": mo.ui.table(tables["facts"], label="Facts"),
                "Reasoning Engines": mo.ui.table(
                    tables["mechanisms"], label="Reasoning Engines"
                ),
                "Claims scale": mo.ui.table(
                    tables["claims_scale_profiles"], label="Claims scale profiles"
                ),
            }
        )
        styled_tabs = mo.style(
            evidence_tabs,
            width="100%",
            min_width="0",
            overflow_x="auto",
        )
        result_view = mo.style(
            mo.vstack(
                [
                    summary,
                    activity_view,
                    mo.md("## Inspect Evidence"),
                    styled_tabs,
                    visual_evidence,
                    mo.accordion(
                        {
                            "Raw JSON": mo.md(
                                f"""```json
{json.dumps(record, indent=2, sort_keys=True)}
```"""
                            )
                        }
                    ),
                ]
            ),
            width="100%",
            min_width="0",
            overflow_x="hidden",
        )
    result_view


if __name__ == "__main__":
    app.run()
