"""Contract tests for the ordinary-Python Marimo reasoning-lab frontend."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "marimo" / "reasoning_lab.py"
CORE = ROOT / "marimo" / "frontend_core.py"
WIDGET_JS = ROOT / "marimo" / "run_activity.js"
PYTHON_ROOT = ROOT / "python"
REPO_ROOT = ROOT.parents[2]


def load_frontend():
    spec = importlib.util.spec_from_file_location("reasoning_lab", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_core():
    spec = importlib.util.spec_from_file_location("frontend_core", CORE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def submitted_configuration() -> dict:
    return {
        "scenario": "car-wash",
        "mode": "live",
        "provider": "ollama",
        "model": "llama3:8b",
        "mechanisms": ["clips"],
        "max_repair_attempts": 3,
    }


def requested_interaction(**changes) -> dict:
    value = {
        "id": "llm-0001",
        "linked_event_ids": ["event-0001"],
        "response_attempt": 1,
        "phase": "initial_recommendation",
        "source": "live",
        "provider": "ollama",
        "model": "llama3:8b",
        "status": "requested",
        "requested_at_utc": "2026-08-04T15:30:00.12Z",
        "completed_at_utc": None,
        "messages": [
            {"role": "system", "content": "Answer directly."},
            {"role": "user", "content": "Choose a safe route."},
        ],
        "response_content": None,
        "safe_error": None,
    }
    value.update(changes)
    return value


def received_interaction(**changes) -> dict:
    value = {
        **requested_interaction(),
        "linked_event_ids": ["event-0001", "event-0002"],
        "status": "received",
        "completed_at_utc": "2026-08-04T15:30:01.34Z",
        "response_content": "Use the certified route.",
    }
    value.update(changes)
    return value


def test_import_exposes_an_ordinary_marimo_app_without_running_analysis() -> None:
    frontend = load_frontend()
    assert frontend.app is not None
    response = load_core().analyze_request(
        scenario="cold-chain", selected_guardrails=("clips", "bn"), analyze=False
    )
    assert response["record"] is None
    assert response["mode"] == "fixture"
    assert "Analyze" in response["message"]


def test_submission_gate_executes_once_per_generation() -> None:
    """Catches Marimo reactivity repeating an already-submitted analysis."""

    calls: list[dict[str, object]] = []
    frontend = load_core()
    gate = frontend.AnalysisSubmissionGate(
        analyze=lambda request, **_kwargs: calls.append(request) or {"record": None}
    )
    request = {
        "scenario": "cold-chain",
        "mode": "fixture",
        "provider": None,
        "model": None,
        "mechanisms": ["clips", "bn"],
        "max_repair_attempts": 3,
    }

    first = gate.evaluate(
        1, request, provider_availability=[], mechanism_availability=[]
    )
    second = gate.evaluate(
        1,
        {**request, "scenario": "car-wash"},
        provider_availability=[{"id": "openai", "enabled": True}],
        mechanism_availability=[{"id": "solver", "enabled": True}],
    )

    assert first is second
    assert calls == [request]


def test_submission_gate_adds_ui_only_utc_timing_receipt() -> None:
    """Catches non-deterministic timestamps leaking into the canonical record."""

    frontend = load_core()
    monotonic_values = iter((10.0, 10.375))
    utc_values = iter(
        (
            datetime(2026, 8, 3, 21, 4, 5, 129_999, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 21, 4, 6, 987_654, tzinfo=timezone.utc),
        )
    )
    canonical = {"scenario": {"id": "car-wash"}}
    gate = frontend.AnalysisSubmissionGate(
        analyze=lambda *_args, **_kwargs: {"record": canonical},
        monotonic=lambda: next(monotonic_values),
        utcnow=lambda: next(utc_values),
    )

    response = gate.evaluate(
        1,
        {
            "scenario": "car-wash",
            "mode": "fixture",
            "mechanisms": ["clips"],
            "max_repair_attempts": 3,
        },
        provider_availability=[],
        mechanism_availability=[],
    )

    assert response["record"] is canonical
    assert response["run_receipt"] == {
        "started_at_utc": "2026-08-03T21:04:05.12Z",
        "completed_at_utc": "2026-08-03T21:04:06.98Z",
        "elapsed_ms": 375,
        "status": "completed",
    }
    assert "started_at_utc" not in canonical


def test_failed_live_gate_reports_observed_provider_responses() -> None:
    """Catches a failed record erasing provider-contact evidence from the receipt."""

    frontend = load_core()

    def failed_live_run(_request, *, interaction_sink, **_kwargs):
        interaction_sink(requested_interaction())
        interaction_sink(received_interaction())
        return {
            "mode": "live",
            "record": None,
            "execution": {
                "llm_source": "none",
                "provider_contacted": False,
                "message": "No completed provider-backed record is available.",
            },
            "message": "Structured facts could not be validated.",
        }

    gate = frontend.AnalysisSubmissionGate(analyze=failed_live_run)
    response = gate.evaluate(
        1,
        submitted_configuration(),
        provider_availability=[{"id": "ollama", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )

    assert response["record"] is None
    assert response["execution"] == {
        "llm_source": "nxuskit-cli / Rust Ollama provider",
        "provider_contacted": True,
        "message": (
            "1 provider response was received through nxuskit-cli / Rust Ollama "
            "provider, but no validated record was produced."
        ),
    }


@pytest.mark.parametrize(
    ("elapsed_ms", "expected"),
    [
        (0, "00:00:00.000"),
        (9_217, "00:00:09.217"),
        (523_000, "00:08:43.000"),
        (3_723_217, "01:02:03.217"),
    ],
)
def test_completed_duration_is_hour_minute_second_millisecond(
    elapsed_ms: int, expected: str
) -> None:
    assert load_core().format_elapsed_duration(elapsed_ms) == expected


@pytest.mark.parametrize("elapsed_ms", [-1, True, 1.5, "1000", None])
def test_completed_duration_rejects_non_integer_or_negative_values(elapsed_ms) -> None:
    with pytest.raises(ValueError, match="elapsed_ms must be a non-negative integer"):
        load_core().format_elapsed_duration(elapsed_ms)


def test_summary_duration_uses_the_authoritative_millisecond_receipt() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'format_elapsed_duration(run_receipt["elapsed_ms"])' in source
    assert 'run_receipt["elapsed_ms"] / 1000' not in source


def test_submission_gate_forwards_each_run_event_once() -> None:
    frontend = load_core()
    forwarded = []

    def analyze(_request, *, event_sink, **_kwargs):
        event_sink(
            {
                "sequence": 1,
                "timestamp_utc": "2026-08-03T21:04:05.12Z",
                "category": "run",
                "status": "completed",
                "message": "Analysis completed.",
            }
        )
        return {"record": {"scenario": {"id": "car-wash"}}}

    gate = frontend.AnalysisSubmissionGate(analyze=analyze)

    response = gate.evaluate(
        1,
        {
            "scenario": "car-wash",
            "mode": "fixture",
            "mechanisms": ["clips"],
            "max_repair_attempts": 3,
        },
        provider_availability=[],
        mechanism_availability=[],
        event_sink=forwarded.append,
    )

    assert response["run_events"] == forwarded
    assert [item["sequence"] for item in forwarded] == [1]


def test_submission_gate_forwards_updates_and_returns_latest_interactions() -> None:
    forwarded = []

    def analyze(_request, *, interaction_sink, **_kwargs):
        interaction_sink(requested_interaction())
        interaction_sink(received_interaction())
        return {"record": {"scenario": {"id": "car-wash"}}}

    gate = load_core().AnalysisSubmissionGate(analyze=analyze)
    response = gate.evaluate(
        1,
        submitted_configuration(),
        provider_availability=[],
        mechanism_availability=[],
        interaction_sink=forwarded.append,
    )

    assert [item["status"] for item in forwarded] == ["requested", "received"]
    assert response["llm_interactions"] == [forwarded[-1]]


def test_submission_gate_rejects_out_of_order_interaction_ids() -> None:
    def analyze(_request, *, interaction_sink, **_kwargs):
        interaction_sink(requested_interaction(id="llm-0002"))
        return {"record": {"scenario": {"id": "car-wash"}}}

    gate = load_core().AnalysisSubmissionGate(analyze=analyze)

    with pytest.raises(ValueError, match="contiguous"):
        gate.evaluate(
            1,
            submitted_configuration(),
            provider_availability=[],
            mechanism_availability=[],
        )


def test_submission_gate_interaction_copies_are_isolated() -> None:
    emitted = requested_interaction()

    def analyze(_request, *, interaction_sink, **_kwargs):
        interaction_sink(emitted)
        emitted["messages"][1]["content"] = "mutated after emission"
        return {"record": {"scenario": {"id": "car-wash"}}}

    response = (
        load_core()
        .AnalysisSubmissionGate(analyze=analyze)
        .evaluate(
            1,
            submitted_configuration(),
            provider_availability=[],
            mechanism_availability=[],
        )
    )

    assert response["llm_interactions"][0]["messages"][1]["content"] == (
        "Choose a safe route."
    )


def test_fixture_submission_compacts_real_interactions_and_linked_events() -> None:
    frontend = load_core()
    forwarded_interactions = []
    forwarded_events = []

    response = frontend.AnalysisSubmissionGate(
        analyze=frontend.analyze_request
    ).evaluate(
        1,
        {
            **submitted_configuration(),
            "mode": "fixture",
            "provider": None,
            "model": None,
        },
        provider_availability=[],
        mechanism_availability=[{"id": "clips", "enabled": True}],
        event_sink=forwarded_events.append,
        interaction_sink=forwarded_interactions.append,
    )

    assert [item["phase"] for item in response["llm_interactions"]] == [
        "initial_recommendation",
        "fact_extraction",
        "repaired_recommendation",
        "fact_extraction",
    ]
    assert all(item["source"] == "fixture" for item in response["llm_interactions"])
    assert [event["id"] for event in forwarded_events] == [
        f"event-{index:04d}" for index in range(1, len(forwarded_events) + 1)
    ]
    assert {item["id"] for item in forwarded_interactions} == {
        "llm-0001",
        "llm-0002",
        "llm-0003",
        "llm-0004",
    }
    assert response["llm_interactions"][-1]["id"] == "llm-0004"


def test_marimo_app_wires_activity_export_and_authoritative_elapsed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "from run_activity import RunActivity" in source
    assert "run_activity_widget = RunActivity()" in source
    assert "run_activity_widget.set_draft_configuration(draft_configuration)" in source
    assert "run_activity_widget.begin_run(" in source
    assert "generation=submit_generation" in source
    assert "event_sink=run_activity_widget.append_event" in source
    assert "interaction_sink=run_activity_widget.append_interaction_update" in source
    assert "run_activity_widget.complete_run(response)" in source
    assert "run_activity_widget.fail_run(" in source
    assert "reasoning_widget.completed_elapsed_ms = int(" in source
    assert "activity_view" in source


def test_result_layout_and_export_documentation_match_the_approved_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    readme = (SCRIPT.parent / "README.md").read_text(encoding="utf-8")

    result_layout = source.split("result_view = mo.style(", 1)[1]
    assert result_layout.index("summary") < result_layout.index("activity_view")
    assert result_layout.index("activity_view") < result_layout.index(
        'mo.md("## Inspect Evidence")'
    )
    assert result_layout.index('mo.md("## Inspect Evidence")') < result_layout.index(
        "visual_evidence"
    )
    for expected in (
        "Run Activity",
        "LLM Interactions",
        "System Prompt",
        "User Prompt",
        "fact-extraction",
        "non-streaming",
        "automatically resumes",
        "down-arrow",
        "Normal, Expanded, and Collapsed",
        "Expanded and Collapsed",
        "schema version `2.0.0`",
        "Original settings + results",
        "Draft settings only",
        "settings-only",
        "schema version `1.0.0`",
        "Import is not yet implemented",
    ):
        assert expected in readme


def test_widget_titles_are_title_case() -> None:
    widget_source = WIDGET_JS.read_text(encoding="utf-8")

    assert '"Run Activity"' in widget_source
    assert '"LLM Interactions"' in widget_source


def test_submitted_request_forwards_provider_model_and_events_to_runner(
    monkeypatch,
) -> None:
    frontend = load_core()
    captured = {}
    emitted = []

    def build_record(*_args, **kwargs):
        captured.update(kwargs)
        kwargs["event_sink"](
            {
                "sequence": 1,
                "timestamp_utc": "2026-08-03T21:04:05.12Z",
                "category": "run",
                "status": "completed",
                "message": "Analysis completed.",
            }
        )
        return {"provenance": {"mode": "live"}}

    monkeypatch.delenv("NXUSKIT_COMMON_SENSE_FIXTURE_LLM", raising=False)
    monkeypatch.setattr(frontend, "build_reasoning_record", build_record)

    frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "live",
            "provider": "ollama",
            "model": "llama3:8b",
            "mechanisms": ["clips"],
            "max_repair_attempts": 3,
        },
        submitted=True,
        provider_availability=[{"id": "ollama", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
        event_sink=emitted.append,
    )

    assert captured["provider_id"] == "ollama"
    assert captured["model_id"] == "llama3:8b"
    assert emitted[0]["message"] == "Analysis completed."


def test_claims_request_emits_an_offline_activity_sequence() -> None:
    frontend = load_core()
    emitted = []

    frontend.analyze_request(
        {
            "scenario": "synthetic-claims-audit",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["claims-audit"],
            "max_repair_attempts": 1,
        },
        submitted=True,
        provider_availability=[],
        mechanism_availability=[{"id": "claims-audit", "enabled": True}],
        event_sink=emitted.append,
    )

    assert [(item["category"], item["status"]) for item in emitted] == [
        ("run", "started"),
        ("facts", "completed"),
        ("engine", "started"),
        ("engine", "accepted"),
        ("run", "accepted"),
    ]


def test_claims_submission_has_a_truthful_empty_interaction_list() -> None:
    frontend = load_core()

    response = frontend.AnalysisSubmissionGate(
        analyze=frontend.analyze_request
    ).evaluate(
        1,
        {
            "scenario": "synthetic-claims-audit",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["claims-audit"],
            "max_repair_attempts": 1,
        },
        provider_availability=[],
        mechanism_availability=[{"id": "claims-audit", "enabled": True}],
    )

    assert response["llm_interactions"] == []


def test_marimo_app_runs_the_selector_dependency_graph_without_a_provider(
    monkeypatch,
) -> None:
    """Catches helpers omitted from a Marimo import cell's returned bindings."""

    frontend = load_frontend()
    availability = __import__("availability")
    monkeypatch.setattr(
        availability,
        "released_license_status",
        lambda *, environ: {
            "token_detected": False,
            "validated": False,
            "features": [],
        },
    )

    outputs, definitions = frontend.app.run()

    assert outputs
    assert type(outputs[-1]).__name__ == "_FlexContainerHtml"
    assert "controls" in definitions


def test_submitted_live_runtime_error_returns_a_safe_callout_response(
    monkeypatch,
) -> None:
    """Catches live structured-output validation failures escaping the UI boundary."""

    frontend = load_core()
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError(
                "StructuredJsonError: provider response included secret-output"
            )
        ),
    )

    response = frontend.analyze_request(
        {
            "scenario": "cold-chain",
            "mode": "live",
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "mechanisms": ["clips", "bn"],
            "max_repair_attempts": 3,
        },
        submitted=True,
        provider_availability=[{"id": "claude", "enabled": True}],
        mechanism_availability=[
            {"id": "clips", "enabled": True},
            {"id": "bn", "enabled": True},
        ],
    )

    assert response["record"] is None
    assert response["message"] == (
        "Live analysis could not validate the provider's structured result. "
        "Check the selected provider and model, then try Analyze again."
    )
    assert "StructuredJsonError" not in response["message"]
    assert "secret-output" not in response["message"]


def test_submitted_live_structured_validation_error_explains_completed_responses(
    monkeypatch,
) -> None:
    """Catches validation exhaustion being described as a provider interruption."""

    frontend = load_core()
    from main import StructuredJsonError

    def fail_after_responses(*_args, **_kwargs):
        try:
            raise StructuredJsonError("secret carrier mismatch")
        except StructuredJsonError as exc:
            raise RuntimeError("live execution failed") from exc

    monkeypatch.setattr(frontend, "build_reasoning_record", fail_after_responses)

    response = frontend.analyze_request(
        {
            "scenario": "cold-chain",
            "mode": "live",
            "provider": "ollama",
            "model": "gemma4:12b",
            "mechanisms": ["clips", "bn", "zen"],
            "max_repair_attempts": 3,
        },
        submitted=True,
        provider_availability=[{"id": "ollama", "enabled": True}],
        mechanism_availability=[
            {"id": "clips", "enabled": True},
            {"id": "bn", "enabled": True},
            {"id": "zen", "enabled": True},
        ],
    )

    assert response["record"] is None
    assert response["message"] == (
        "Live provider responses were received, but their structured facts did not "
        "satisfy the required contract after repair. Review LLM Interactions or "
        "choose another model, then try Analyze again."
    )
    assert "secret" not in response["message"]


def test_fixture_community_request_matches_the_canonical_cold_chain_record() -> None:
    frontend = load_core()
    sys.path.insert(0, str(PYTHON_ROOT))
    from main import build_reasoning_record

    response = frontend.analyze_request(
        scenario="cold-chain", selected_guardrails=("clips", "bn"), analyze=True
    )
    assert response["record"] == build_reasoning_record(
        "cold-chain", "mock", "ce", "clips,bn"
    )
    assert response["record"]["provenance"]["mode"] == "fixture"


def test_claims_frontend_path_is_offline_and_review_oriented() -> None:
    frontend = load_core()
    response = frontend.analyze_request(
        scenario="synthetic-claims-audit",
        selected_guardrails=("claims-audit",),
        analyze=True,
    )
    assert response["record"]["scenario"]["id"] == "synthetic-claims-audit"
    assert response["record"]["final"]["review_disposition"] == "review_required"
    assert response["pro_availability"] == []


def test_claims_audit_rejects_provider_backed_modes_before_contact() -> None:
    """Catches the offline audit presenting Auto or Live as provider execution."""

    frontend = load_core()
    with pytest.raises(
        ValueError, match="synthetic claims audit supports Fixture only"
    ):
        frontend.analyze_request(
            {
                "scenario": "synthetic-claims-audit",
                "mode": "live",
                "provider": "claude",
                "model": "claude-haiku-4-5",
                "mechanisms": ["claims-audit"],
                "max_repair_attempts": 2,
            },
            submitted=True,
            provider_availability=[{"id": "claude", "enabled": True}],
            mechanism_availability=[{"id": "claims-audit", "enabled": True}],
        )


def test_explicit_pro_selection_degrades_truthfully_without_a_pro_invocation() -> None:
    frontend = load_core()
    response = frontend.analyze_request(
        scenario="cold-chain", selected_guardrails=("clips", "zen"), analyze=True
    )
    assert response["record"] is not None
    assert response["effective_guardrails"] == ["clips"]
    assert response["pro_availability"] == [
        {
            "id": "zen",
            "tier": "pro",
            "selected": True,
            "available": False,
            "reason": "The fixture frontend does not invoke Pro mechanisms.",
        }
    ]


def test_script_mode_requires_an_explicit_analyze_flag() -> None:
    idle = subprocess.run(
        [sys.executable, str(CORE), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(idle.stdout)["record"] is None

    analyzed = subprocess.run(
        [
            sys.executable,
            str(CORE),
            "--json",
            "--analyze",
            "--scenario",
            "synthetic-claims-audit",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert (
        json.loads(analyzed.stdout)["record"]["scenario"]["id"]
        == "synthetic-claims-audit"
    )


def test_manifest_registers_the_frontend_without_changing_language_parity() -> None:
    manifest = json.loads(
        (REPO_ROOT / "conformance" / "examples_manifest.json").read_text()
    )
    entry = next(
        item
        for item in manifest["examples"]
        if item["name"] == "common-sense-guardrails"
    )
    assert entry["languages"] == ["python", "bash"]
    assert entry["frontends"] == [
        {
            "id": "reasoning-lab",
            "kind": "marimo",
            "language": "python",
            "entrypoint": "examples/integrations/common-sense-guardrails/marimo/reasoning_lab.py",
            "documentation": "examples/integrations/common-sense-guardrails/marimo/README.md",
            "default_mode": "fixture",
            "community_offline": True,
            "requires_explicit_analyze": True,
        }
    ]


def test_phase_two_selector_exposes_exactly_the_five_approved_scenarios() -> None:
    """Catches a workbench selector that silently omits an approved scenario."""

    assert load_core().SCENARIOS == (
        "car-wash",
        "coupon-stack",
        "pallet-door",
        "cold-chain",
        "synthetic-claims-audit",
    )


def test_car_wash_default_selection_excludes_unsupported_bn() -> None:
    """Catches a stale UI default that selects an unsupported Bayesian mechanism."""

    availability = [
        {"id": "clips", "enabled": True},
        {"id": "bn", "enabled": False},
        {"id": "solver", "enabled": True},
        {"id": "zen", "enabled": False},
    ]

    assert load_core().default_mechanisms("car-wash", availability) == [
        "clips",
        "solver",
    ]


def fully_entitled_availability() -> list[dict[str, object]]:
    return [
        {"id": engine, "enabled": True}
        for engine in ("clips", "bn", "solver", "zen", "claims-audit")
    ]


@pytest.mark.parametrize(
    ("scenario", "selected"),
    [
        ("car-wash", []),
        ("car-wash", ["bn", "zen"]),
        ("synthetic-claims-audit", ["clips", "solver"]),
    ],
)
def test_engine_resolver_never_inserts_defaults_for_empty_effective_selection(
    scenario, selected
) -> None:
    applied, _skipped = load_core().resolve_reasoning_engines(
        scenario, selected, fully_entitled_availability()
    )

    assert applied == []


def test_submitted_empty_effective_selection_stops_before_runner(monkeypatch) -> None:
    frontend = load_core()
    calls = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(
        ValueError,
        match="select at least one available Reasoning Engine that applies",
    ):
        frontend.analyze_request(
            {
                "scenario": "car-wash",
                "mode": "live",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "mechanisms": [],
                "max_repair_attempts": 3,
            },
            submitted=True,
            provider_availability=[{"id": "claude", "enabled": True}],
            mechanism_availability=fully_entitled_availability(),
        )

    assert calls == []


@pytest.mark.parametrize(
    ("scenario", "selected", "expected_applied", "expected_skipped"),
    [
        (
            "car-wash",
            ["clips", "bn", "solver", "zen"],
            ["clips", "solver"],
            ["bn", "zen"],
        ),
        (
            "cold-chain",
            ["clips", "bn", "solver", "zen"],
            ["clips", "bn", "zen"],
            ["solver"],
        ),
        (
            "synthetic-claims-audit",
            ["clips", "solver"],
            [],
            ["clips", "solver"],
        ),
    ],
)
def test_analyze_uses_only_available_applicable_explicit_subset(
    scenario, selected, expected_applied, expected_skipped
) -> None:
    """Catches stale or inapplicable selections reaching a submitted engine run."""

    applied, skipped = load_core().resolve_reasoning_engines(
        scenario, selected, fully_entitled_availability()
    )

    assert applied == expected_applied
    assert [item["id"] for item in skipped] == expected_skipped


def test_submitted_analysis_passes_only_applied_engines_and_reports_skipped(
    monkeypatch,
) -> None:
    """Catches the submitted runner bypassing the availability/applicability resolver."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: calls.append(args) or {},
    )

    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["clips", "bn", "solver", "zen"],
            "max_repair_attempts": 3,
        },
        submitted=True,
        mechanism_availability=fully_entitled_availability(),
    )

    assert calls == [("car-wash", "mock", None, "clips,solver", 3)]
    assert response["effective_guardrails"] == ["clips", "solver"]
    assert response["skipped_mechanisms"] == [
        {"id": "bn", "reason": "unsupported_for_scenario"},
        {"id": "zen", "reason": "unsupported_for_scenario"},
    ]


def test_unsubmitted_phase_two_request_invokes_no_canonical_runner(monkeypatch) -> None:
    """Catches reactive configuration changes that execute a runner before Analyze."""

    frontend = load_core()
    invoked: list[object] = []
    monkeypatch.setattr(
        frontend, "build_reasoning_record", lambda *args, **kwargs: invoked.append(args)
    )
    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["clips"],
            "max_repair_attempts": 3,
        },
        submitted=False,
    )
    assert response["record"] is None
    assert invoked == []


def test_submitted_fixture_request_preserves_canonical_record_identity() -> None:
    """Catches a frontend implementation that creates a second fixture authority."""

    frontend = load_core()
    response = frontend.analyze_request(
        {
            "scenario": "cold-chain",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["clips", "bn"],
            "max_repair_attempts": 3,
        },
        submitted=True,
    )
    assert response["record"] == frontend.build_reasoning_record(
        "cold-chain", "mock", None, "clips,bn", 3
    )


def test_fixture_submission_skips_unavailable_or_incompatible_mechanisms(
    monkeypatch,
) -> None:
    """Catches stale fixture selections reaching the canonical runner unchanged."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: calls.append(args) or {},
    )

    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "fixture",
            "provider": None,
            "model": None,
            "mechanisms": ["clips", "bn", "solver"],
            "max_repair_attempts": 3,
        },
        submitted=True,
        mechanism_availability=[
            {"id": "clips", "enabled": True},
            {"id": "bn", "enabled": False},
            {"id": "solver", "enabled": False},
            {"id": "zen", "enabled": False},
        ],
    )

    assert response["effective_guardrails"] == ["clips"]
    assert calls == [("car-wash", "mock", None, "clips", 3)]


@pytest.mark.parametrize("mechanisms", [[], ["bn", "solver", "zen"]])
def test_fixture_submission_rejects_empty_or_unsupported_mechanisms(
    monkeypatch, mechanisms
) -> None:
    """Catches an empty or stale fixture selector silently inserting CLIPS."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: calls.append(args) or {},
    )

    with pytest.raises(
        ValueError,
        match="select at least one available Reasoning Engine that applies",
    ):
        frontend.analyze_request(
            {
                "scenario": "car-wash",
                "mode": "fixture",
                "provider": None,
                "model": None,
                "mechanisms": mechanisms,
                "max_repair_attempts": 3,
            },
            submitted=True,
            mechanism_availability=[
                {"id": "clips", "enabled": True},
                {"id": "bn", "enabled": False},
                {"id": "solver", "enabled": False},
                {"id": "zen", "enabled": False},
            ],
        )

    assert calls == []


def test_submitted_live_request_delegates_with_scoped_provider_and_model(
    monkeypatch,
) -> None:
    """Catches dropped live request fields or provider state that persists after a run."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []

    def canonical_runner(*args, **_kwargs):
        calls.append(
            (*args, os.environ.get("NXUSKIT_PROVIDER"), os.environ.get("NXUSKIT_MODEL"))
        )
        return {"canonical": True}

    monkeypatch.delenv("NXUSKIT_PROVIDER", raising=False)
    monkeypatch.delenv("NXUSKIT_MODEL", raising=False)
    monkeypatch.setattr(frontend, "build_reasoning_record", canonical_runner)
    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "live",
            "provider": "ollama",
            "model": "fixture-model",
            "mechanisms": ["clips"],
            "max_repair_attempts": 2,
        },
        submitted=True,
        provider_availability=[{"id": "ollama", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )
    assert response["record"] == {"canonical": True}
    assert calls == [("car-wash", "live", None, "clips", 2, "ollama", "fixture-model")]
    assert "NXUSKIT_PROVIDER" not in os.environ
    assert "NXUSKIT_MODEL" not in os.environ


def test_live_fixture_override_is_rejected_before_provider_or_runner_contact(
    monkeypatch,
) -> None:
    """Catches deterministic smoke configuration masquerading as a Live run."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setenv("NXUSKIT_COMMON_SENSE_FIXTURE_LLM", "1")
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: calls.append(args) or {"provenance": {"mode": "live"}},
    )

    with pytest.raises(ValueError, match="provider-backed modes are disabled"):
        frontend.analyze_request(
            {
                "scenario": "car-wash",
                "mode": "live",
                "provider": "claude",
                "model": "claude-haiku-4-5",
                "mechanisms": ["clips"],
                "max_repair_attempts": 2,
            },
            submitted=True,
            provider_availability=[{"id": "claude", "enabled": True}],
            mechanism_availability=[{"id": "clips", "enabled": True}],
        )

    assert calls == []


def test_coupon_auto_uses_fixture_before_provider_validation(monkeypatch) -> None:
    """Catches contained Auto consulting availability or retaining provider identity."""

    frontend = load_core()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fixture_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return {"provenance": {"mode": "fixture"}}

    monkeypatch.delenv("NXUSKIT_COMMON_SENSE_FIXTURE_LLM", raising=False)
    monkeypatch.setattr(
        frontend,
        "_enabled",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("coupon Auto must not validate a provider")
        ),
    )
    monkeypatch.setattr(frontend, "build_reasoning_record", fixture_runner)

    response = frontend.analyze_request(
        {
            "scenario": "coupon-stack",
            "mode": "auto",
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "mechanisms": ["clips"],
            "max_repair_attempts": 3,
        },
        submitted=True,
        provider_availability=[{"id": "claude", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )

    assert response["record"]["provenance"] == {"mode": "fixture"}
    assert response["requested_provider"] is None
    assert response["requested_model"] is None
    assert response["execution"] == {
        "llm_source": "checked-in fixture",
        "provider_contacted": False,
        "resolved_mode": "mock",
        "compatibility_code": (
            "coupon_live_strict_schema_transport_unavailable_v1_0_5"
        ),
        "message": (
            "Coupon stack Auto uses checked-in fixtures with nxusKit v1.0.5 "
            "because the Python provider path cannot preserve the required strict "
            "schema; no provider was contacted."
        ),
    }
    assert calls[0][0][:5] == ("coupon-stack", "mock", None, "clips", 3)
    assert calls[0][1]["provider_id"] is None
    assert calls[0][1]["model_id"] is None
    for forbidden in ("resolved_mode", "provider_contacted", "compatibility_code"):
        assert forbidden not in response["record"]["provenance"]


def test_coupon_live_rejects_before_provider_validation(monkeypatch) -> None:
    """Catches a direct coupon Live submission reaching availability or the runner."""

    frontend = load_core()
    monkeypatch.delenv("NXUSKIT_COMMON_SENSE_FIXTURE_LLM", raising=False)
    monkeypatch.setattr(
        frontend,
        "_enabled",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("coupon Live must not validate a provider")
        ),
    )
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("coupon Live must not invoke the runner")
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "^coupon_live_strict_schema_transport_unavailable_v1_0_5: "
            "coupon-stack live mode is unavailable"
        ),
    ):
        frontend.analyze_request(
            {
                "scenario": "coupon-stack",
                "mode": "live",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "mechanisms": ["clips"],
                "max_repair_attempts": 3,
            },
            submitted=True,
            provider_availability=[{"id": "claude", "enabled": True}],
            mechanism_availability=[{"id": "clips", "enabled": True}],
        )


def test_live_response_discloses_real_nxuskit_provider_contact(monkeypatch) -> None:
    """Catches a completed Live summary that does not state its execution source."""

    frontend = load_core()
    monkeypatch.delenv("NXUSKIT_COMMON_SENSE_FIXTURE_LLM", raising=False)
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *_args, **_kwargs: {"provenance": {"mode": "live"}},
    )

    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "live",
            "provider": "claude",
            "model": "claude-haiku-4-5",
            "mechanisms": ["clips"],
            "max_repair_attempts": 2,
        },
        submitted=True,
        provider_availability=[{"id": "claude", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )

    assert response["execution"] == {
        "llm_source": "nxusKit provider",
        "provider_contacted": True,
        "message": "The selected provider and model were invoked through nxusKit.",
    }


def test_live_ollama_response_discloses_cli_rust_compatibility_backend(
    monkeypatch,
) -> None:
    """Catches a completed v1.0.5 Ollama run hiding its compatibility route."""

    frontend = load_core()
    monkeypatch.delenv("NXUSKIT_COMMON_SENSE_FIXTURE_LLM", raising=False)
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *_args, **_kwargs: {"provenance": {"mode": "live"}},
    )

    response = frontend.analyze_request(
        {
            "scenario": "car-wash",
            "mode": "live",
            "provider": "ollama",
            "model": "gemma4:12b",
            "mechanisms": ["clips"],
            "max_repair_attempts": 2,
        },
        submitted=True,
        provider_availability=[{"id": "ollama", "enabled": True}],
        mechanism_availability=[{"id": "clips", "enabled": True}],
    )

    assert response["execution"] == {
        "llm_source": "nxuskit-cli / Rust Ollama provider",
        "provider_contacted": True,
        "message": (
            "The selected Ollama model was invoked through released nxuskit-cli "
            "and the Rust provider."
        ),
    }


def test_disabled_live_selection_fails_before_the_canonical_runner(monkeypatch) -> None:
    """Catches a disabled provider or mechanism reaching an effectful run boundary."""

    frontend = load_core()
    invoked: list[object] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: invoked.append(args),
    )
    request = {
        "scenario": "cold-chain",
        "mode": "live",
        "provider": "openai",
        "model": "fixture-model",
        "mechanisms": ["clips"],
        "max_repair_attempts": 3,
    }
    with pytest.raises(ValueError, match="disabled provider"):
        frontend.analyze_request(
            request,
            submitted=True,
            provider_availability=[{"id": "openai", "enabled": False}],
            mechanism_availability=[{"id": "clips", "enabled": True}],
        )
    assert invoked == []


def test_unavailable_availability_projection_lists_disabled_status_and_reason() -> None:
    """Catches unavailable options that a closed disabled widget hides from view."""

    projection = load_core().unavailable_availability_markdown(
        "providers",
        [
            {
                "id": "openai",
                "enabled": False,
                "status": "credential_not_detected",
                "reason": "OPENAI_API_KEY was not detected.",
            },
            {
                "id": "ollama",
                "enabled": False,
                "status": "endpoint_unreachable",
                "reason": "Local preflight has not succeeded.",
            },
            {
                "id": "claude",
                "enabled": True,
                "status": "available",
                "reason": "Selectable after Analyze.",
            },
        ],
    )

    assert "## Unavailable providers (disabled)" in projection
    assert (
        "`openai` — disabled / credential_not_detected: OPENAI_API_KEY was not detected."
        in projection
    )
    assert (
        "`ollama` — disabled / endpoint_unreachable: Local preflight has not succeeded."
        in projection
    )
    assert "`claude`" not in projection


def test_reasoning_lab_mode_guidance_distinguishes_controls_and_submitted_modes() -> (
    None
):
    """Catches help text that hides Auto's possible live execution after Analyze."""

    guidance = load_core().mode_guidance()
    assert "Changing controls has no effect." in guidance
    assert "After explicit Analyze:" in guidance
    assert (
        "Fixture — deterministic synthetic evidence; it does not call a provider."
        in guidance
    )
    assert (
        "Auto — may attempt a compatible enabled live provider, then falls back only where supported."
        in guidance
    )
    assert "Live — runs the selected enabled provider." in guidance
    assert "Select at least one available Reasoning Engine" in guidance


@pytest.mark.parametrize("mode", ["fixture", "auto", "live"])
def test_submitted_empty_selection_is_rejected_for_each_mode(monkeypatch, mode) -> None:
    """Catches an empty submitted selection silently inserting default engines."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: calls.append(args) or {},
    )

    with pytest.raises(
        ValueError,
        match="select at least one available Reasoning Engine that applies",
    ):
        frontend.analyze_request(
            {
                "scenario": "car-wash",
                "mode": mode,
                "provider": "ollama" if mode != "fixture" else None,
                "model": None,
                "mechanisms": [],
                "max_repair_attempts": 3,
            },
            submitted=True,
            provider_availability=[{"id": "ollama", "enabled": True}],
            mechanism_availability=[
                {"id": "clips", "enabled": True},
                {"id": "bn", "enabled": False},
                {"id": "solver", "enabled": True},
                {"id": "zen", "enabled": False},
            ],
        )

    assert calls == []


@pytest.mark.parametrize("mode", ["auto", "live"])
def test_nonfixture_stale_selection_is_rejected(monkeypatch, mode) -> None:
    """Catches a stale selection silently inserting another enabled engine."""

    frontend = load_core()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: calls.append(args) or {},
    )

    with pytest.raises(
        ValueError,
        match="select at least one available Reasoning Engine that applies",
    ):
        frontend.analyze_request(
            {
                "scenario": "car-wash",
                "mode": mode,
                "provider": "ollama",
                "model": None,
                "mechanisms": ["bn"],
                "max_repair_attempts": 3,
            },
            submitted=True,
            provider_availability=[{"id": "ollama", "enabled": True}],
            mechanism_availability=[
                {"id": "clips", "enabled": True},
                {"id": "bn", "enabled": False},
                {"id": "solver", "enabled": True},
            ],
        )

    assert calls == []


@pytest.mark.parametrize("mode", ["auto", "live"])
@pytest.mark.parametrize("mechanisms", [[], ["bn"]])
def test_nonfixture_no_enabled_compatible_selection_fails_before_runner(
    monkeypatch, mode, mechanisms
) -> None:
    """Catches Auto/Live falling through to a disabled synthetic CLIPS fallback."""

    frontend = load_core()
    invoked: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        frontend,
        "build_reasoning_record",
        lambda *args, **_kwargs: invoked.append(args) or {},
    )

    with pytest.raises(
        ValueError,
        match="select at least one available Reasoning Engine that applies",
    ):
        frontend.analyze_request(
            {
                "scenario": "car-wash",
                "mode": mode,
                "provider": "ollama",
                "model": None,
                "mechanisms": mechanisms,
                "max_repair_attempts": 3,
            },
            submitted=True,
            provider_availability=[{"id": "ollama", "enabled": True}],
            mechanism_availability=[
                {"id": "clips", "enabled": False},
                {"id": "bn", "enabled": False},
                {"id": "solver", "enabled": False},
            ],
        )

    assert invoked == []


def test_phase_two_ui_uses_the_anywidget_and_generation_gated_result_surface() -> None:
    """Catches restoration of the old form or bypass of the submitted generation gate."""

    source = SCRIPT.read_text(encoding="utf-8")
    assert "mo.ui.anywidget" in source
    assert "ReasoningControls" in source
    assert "ProviderDiscoveryCoordinator" in source
    assert "AnalysisSubmissionGate" in source
    assert "controls.value" in source
    assert "submit_generation" in source
    assert ".form(" not in source
    assert "mo.ui.text" not in source
    assert "mode_guidance" not in source
    assert "unavailable_availability_markdown" not in source
    for label in (
        "Summary",
        "Provider / model",
        "Reasoning Engine execution",
        "Visual Evidence",
        "Findings",
        "Evidence",
        "Attempts",
        "Facts",
        "Reasoning Engines",
        "Raw JSON",
    ):
        assert label in source
    assert "inspect_provider_availability" in source
    assert "inspect_reasoning_engine_availability" in source
    assert "record_tables" in source
    assert "mo.ui.altair_chart" in source
    assert "mo.vstack" in source


def test_result_layout_is_full_width_wrapped_and_overflow_safe() -> None:
    """Catches charts or evidence tabs being clipped in the right-side content area."""

    source = SCRIPT.read_text(encoding="utf-8")

    assert 'width="100%"' in source
    assert 'min_width="0"' in source
    assert 'overflow_x="auto"' in source
    assert "mo.hstack(" in source
    assert "wrap=True" in source
    assert 'widths="equal"' in source


def test_reasoning_lab_uses_responsive_ui_tabs_and_explains_safe_modes() -> None:
    """Catches deprecated tabs or terse controls hiding usable evidence guidance."""

    source = SCRIPT.read_text(encoding="utf-8")
    assert "mo.ui.tabs(" in source
    assert "mo.tabs(" not in source
    assert "Unavailable providers (visible, disabled)" not in source
    assert "Unavailable mechanisms (visible, disabled)" not in source
    assert 'properties(width="container")' in source
    assert "styled_tabs = mo.style(" in source
    assert "evidence_tabs," in source
    assert "chart_views" in source
    assert "mo.hstack(" in source
    assert "\\\\n" not in source


def test_evidence_charts_avoid_invalid_scale_bindings_and_facet_widths() -> None:
    """Catches browser warnings that make categorical or faceted charts look broken."""

    source = SCRIPT.read_text(encoding="utf-8")
    assert "chart_selection=False" in source
    assert "legend_selection=False" in source
    assert 'properties(width="container")' in source
