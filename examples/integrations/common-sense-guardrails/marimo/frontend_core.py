"""Import-safe fixture request core shared by the Marimo and script surfaces."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from claims_audit import build_claims_reasoning_record  # noqa: E402
from llm_interactions import validate_interaction_snapshot  # noqa: E402
from main import StructuredJsonError, build_reasoning_record  # noqa: E402
from run_events import RunEventEmitter  # noqa: E402


SCENARIOS = (
    "car-wash",
    "coupon-stack",
    "pallet-door",
    "cold-chain",
    "synthetic-claims-audit",
)
COMMUNITY_GUARDRAILS = ("clips", "bn")
PRO_GUARDRAILS = ("solver", "zen")
CLAIMS_GUARDRAIL = "claims-audit"
DEFAULT_GUARDRAILS = ("clips", "bn")
FIXTURE_LLM_ENV = "NXUSKIT_COMMON_SENSE_FIXTURE_LLM"
BN_SCENARIOS = {"coupon-stack", "cold-chain"}
COMPATIBLE_GUARDRAILS = {
    "car-wash": ("clips", "solver"),
    "coupon-stack": ("clips", "bn", "zen"),
    "pallet-door": ("clips", "solver"),
    "cold-chain": ("clips", "bn", "zen"),
}
DEFAULT_MECHANISMS = {
    **COMPATIBLE_GUARDRAILS,
    "synthetic-claims-audit": (CLAIMS_GUARDRAIL,),
}
COUPON_COMPATIBILITY_PATH = (
    ROOT / "scenarios" / "coupon-stack" / "mode-compatibility-v1.0.5.json"
)


def coupon_mode_compatibility() -> dict[str, Any]:
    """Load the public v1.0.5 coupon compatibility policy."""

    payload = json.loads(COUPON_COMPATIBILITY_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("scenario") != "coupon-stack"
        or payload.get("sdk_release") != "1.0.5"
        or not isinstance(payload.get("modes"), dict)
    ):
        raise ValueError("invalid coupon mode compatibility policy")
    return payload


def _selected_items(selected_guardrails: Iterable[str] | str) -> list[str]:
    if isinstance(selected_guardrails, str):
        selected = selected_guardrails.split(",")
    else:
        selected = list(selected_guardrails)
    return [item.strip().lower() for item in selected if item and item.strip()]


def _pro_availability(selected: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": item,
            "tier": "pro",
            "selected": True,
            "available": False,
            "reason": "The fixture frontend does not invoke Pro mechanisms.",
        }
        for item in selected
        if item in PRO_GUARDRAILS
    ]


def _effective_guardrails(scenario: str, selected: list[str]) -> list[str]:
    if scenario == "synthetic-claims-audit":
        return [CLAIMS_GUARDRAIL]
    effective = [item for item in selected if item in COMMUNITY_GUARDRAILS]
    return effective or ["clips"]


def _fixture_guardrails(
    scenario: str,
    selected: list[str],
    availability: Sequence[Mapping[str, object]] | None,
) -> list[str]:
    """Keep fixture submissions inside the available Community scenario subset."""

    compatible = {"clips"}
    if scenario in BN_SCENARIOS:
        compatible.add("bn")
    effective = [item for item in selected if item in compatible]
    if availability is not None:
        effective = [item for item in effective if _enabled(item, availability)]
    return effective


def default_mechanisms(
    scenario: str, availability: Sequence[Mapping[str, object]]
) -> list[str]:
    """Select only enabled mechanisms compatible with the current scenario."""

    enabled = {
        str(entry["id"])
        for entry in availability
        if entry.get("enabled") is True and "id" in entry
    }
    return [item for item in DEFAULT_MECHANISMS[scenario] if item in enabled]


def resolve_reasoning_engines(
    scenario: str,
    selected: Iterable[str] | str,
    availability: Sequence[Mapping[str, object]],
) -> tuple[list[str], list[dict[str, str]]]:
    """Resolve selected engines to the enabled scenario subset plus safe skips."""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    applicable_ids = set(COMPATIBLE_GUARDRAILS.get(scenario, (CLAIMS_GUARDRAIL,)))
    enabled_ids = {
        str(item["id"])
        for item in availability
        if item.get("enabled") is True and "id" in item
    }
    selected_ids = _selected_items(selected)
    applied = [
        item for item in selected_ids if item in applicable_ids and item in enabled_ids
    ]
    skipped = [
        {
            "id": item,
            "reason": (
                "unavailable" if item not in enabled_ids else "unsupported_for_scenario"
            ),
        }
        for item in selected_ids
        if item not in applied
    ]
    return applied, skipped


class AnalysisSubmissionGate:
    """Execute the canonical analyzer at most once for each submitted generation."""

    def __init__(
        self,
        analyze: Callable[..., dict[str, Any]] | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._analyze = analyze or analyze_request
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._generation = 0
        self._response: dict[str, Any] | None = None

    def evaluate(
        self,
        generation: int,
        request: Mapping[str, Any],
        *,
        provider_availability: Sequence[Mapping[str, object]],
        mechanism_availability: Sequence[Mapping[str, object]],
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        interaction_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if generation < 1:
            raise ValueError("submission generation must be positive")
        if generation == self._generation and self._response is not None:
            return self._response
        if generation < self._generation:
            raise ValueError("submission generation cannot move backwards")
        started_at = self._utcnow()
        started = self._monotonic()
        run_events: list[dict[str, Any]] = []
        latest_interactions: dict[str, dict[str, Any]] = {}

        def capture_event(event: dict[str, Any]) -> None:
            copied = json.loads(json.dumps(event))
            run_events.append(copied)
            if event_sink is not None:
                event_sink(json.loads(json.dumps(copied)))

        def capture_interaction(snapshot: dict[str, Any]) -> None:
            interaction_id = snapshot.get("id")
            previous = latest_interactions.get(interaction_id)
            if previous is None:
                expected_id = f"llm-{len(latest_interactions) + 1:04d}"
                if interaction_id != expected_id:
                    raise ValueError("LLM interaction IDs must be contiguous")
            safe = validate_interaction_snapshot(snapshot, previous=previous)
            latest_interactions[safe["id"]] = safe
            if interaction_sink is not None:
                interaction_sink(json.loads(json.dumps(safe, ensure_ascii=False)))

        analyzed = self._analyze(
            dict(request),
            submitted=True,
            provider_availability=provider_availability,
            mechanism_availability=mechanism_availability,
            event_sink=capture_event,
            interaction_sink=capture_interaction,
        )
        completed = self._monotonic()
        completed_at = self._utcnow()
        response = dict(analyzed)
        response["run_events"] = run_events
        response["llm_interactions"] = json.loads(
            json.dumps(list(latest_interactions.values()), ensure_ascii=False)
        )
        received_count = sum(
            item.get("source") == "live" and item.get("status") == "received"
            for item in latest_interactions.values()
        )
        if response.get("record") is None and received_count:
            noun = "response was" if received_count == 1 else "responses were"
            execution_source = provider_execution_source(request.get("provider"))
            response["execution"] = {
                "llm_source": execution_source,
                "provider_contacted": True,
                "message": (
                    f"{received_count} provider {noun} received through "
                    f"{execution_source}, but "
                    "no validated record was produced."
                ),
            }
        response["run_receipt"] = {
            "started_at_utc": _utc_iso(started_at),
            "completed_at_utc": _utc_iso(completed_at),
            "elapsed_ms": round((completed - started) * 1_000),
            "status": "completed" if response.get("record") is not None else "failed",
        }
        self._generation = generation
        self._response = response
        return response


def _utc_iso(value: datetime) -> str:
    """Render an explicit UTC instant without touching the canonical record."""

    utc_value = value.astimezone(timezone.utc)
    hundredths = utc_value.microsecond // 10_000
    whole_seconds = utc_value.replace(microsecond=0).isoformat().removesuffix("+00:00")
    return f"{whole_seconds}.{hundredths:02d}Z"


def format_elapsed_duration(elapsed_ms: int) -> str:
    """Render an authoritative non-negative millisecond duration."""

    if (
        isinstance(elapsed_ms, bool)
        or not isinstance(elapsed_ms, int)
        or elapsed_ms < 0
    ):
        raise ValueError("elapsed_ms must be a non-negative integer")
    hours, remainder = divmod(elapsed_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def provider_execution_source(provider: object) -> str:
    """Return a fixed non-secret backend label for UI and export receipts."""

    if str(provider or "").lower() == "ollama":
        return "nxuskit-cli / Rust Ollama provider"
    return "nxusKit provider"


def _execution_summary(
    scenario: str,
    mode: str,
    record: Mapping[str, Any] | None,
    provider: object = None,
) -> dict[str, object]:
    """Describe provider contact truthfully outside the deterministic record."""

    if scenario == "synthetic-claims-audit":
        return {
            "llm_source": "offline synthetic audit",
            "provider_contacted": False,
            "message": "This scenario is deterministic and does not invoke an LLM provider.",
        }
    if scenario == "coupon-stack" and mode == "auto":
        compatibility = coupon_mode_compatibility()
        modes = compatibility["modes"]
        assert isinstance(modes, dict)
        auto = modes["auto"]
        assert isinstance(auto, dict)
        return {
            "llm_source": "checked-in fixture",
            "provider_contacted": False,
            "resolved_mode": "mock",
            "compatibility_code": compatibility["compatibility_code"],
            "message": auto["message"],
        }
    if mode == "fixture":
        return {
            "llm_source": "checked-in fixture",
            "provider_contacted": False,
            "message": "No LLM provider was invoked.",
        }
    if record is None:
        return {
            "llm_source": "none",
            "provider_contacted": False,
            "message": "No completed provider-backed record is available.",
        }
    resolved = str(record.get("provenance", {}).get("mode", ""))
    if mode == "auto" and resolved != "live":
        return {
            "llm_source": "checked-in fixture fallback",
            "provider_contacted": False,
            "message": "Auto did not resolve to a live provider and used its supported fixture fallback.",
        }
    execution_source = provider_execution_source(provider)
    if execution_source == "nxuskit-cli / Rust Ollama provider":
        message = (
            "The selected Ollama model was invoked through released nxuskit-cli "
            "and the Rust provider."
        )
    else:
        message = "The selected provider and model were invoked through nxusKit."
    return {
        "llm_source": execution_source,
        "provider_contacted": True,
        "message": message,
    }


def unavailable_availability_markdown(
    kind: str, availability: Sequence[Mapping[str, object]]
) -> str:
    """Render unavailable options so their disabled state never depends on a widget."""

    lines = [f"## Unavailable {kind} (disabled)"]
    unavailable = [entry for entry in availability if entry.get("enabled") is not True]
    if not unavailable:
        return "\n".join([*lines, "- None for this scenario."])
    lines.extend(
        f"- `{entry.get('id', 'unknown')}` — disabled / "
        f"{entry.get('status', 'unavailable')}: {entry.get('reason', '')}"
        for entry in unavailable
    )
    return "\n".join(lines)


def mode_guidance() -> str:
    """Describe effect boundaries and submitted behavior without invoking a provider."""

    return """**Mode guidance**

Changing controls has no effect. After explicit Analyze:

- Fixture — deterministic synthetic evidence; it does not call a provider.
- Auto — may attempt a compatible enabled live provider, then falls back only where supported.
- Live — runs the selected enabled provider.

Select at least one available Reasoning Engine that applies to the scenario. Analyze never inserts an engine for an empty or stale selection.
"""


def _compatible_enabled_guardrails(
    scenario: str,
    selected: list[str],
    availability: Sequence[Mapping[str, object]] | None,
) -> list[str]:
    """Resolve optional Auto/Live selections before the submitted runner boundary."""

    compatible = COMPATIBLE_GUARDRAILS[scenario]
    if availability is None:
        return []
    enabled = [
        str(entry["id"])
        for entry in availability
        if entry.get("enabled") is True and entry.get("id") in compatible
    ]
    selected_enabled = [item for item in selected if item in enabled]
    return selected_enabled


@contextmanager
def _selected_provider_environment(
    provider: str | None, model: str | None
) -> Iterator[None]:
    """Temporarily expose submitted provider selection to the canonical runner."""

    original = {
        name: os.environ.get(name) for name in ("NXUSKIT_PROVIDER", "NXUSKIT_MODEL")
    }
    try:
        if provider is not None:
            os.environ["NXUSKIT_PROVIDER"] = provider
        if model is not None:
            os.environ["NXUSKIT_MODEL"] = model
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _enabled(entry_id: str, entries: Sequence[Mapping[str, object]] | None) -> bool:
    if entries is None:
        return False
    return any(
        item.get("id") == entry_id and item.get("enabled") is True for item in entries
    )


def _submitted_request(
    request: Mapping[str, Any],
    *,
    submitted: bool,
    provider_availability: Sequence[Mapping[str, object]] | None,
    mechanism_availability: Sequence[Mapping[str, object]] | None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    interaction_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    scenario = str(request.get("scenario", ""))
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    mode = str(request.get("mode", "fixture"))
    if mode not in {"fixture", "auto", "live"}:
        raise ValueError("mode must be fixture, auto, or live")
    provider = request.get("provider")
    model = request.get("model")
    if submitted and scenario == "coupon-stack":
        compatibility = coupon_mode_compatibility()
        if mode == "live":
            raise RuntimeError(str(compatibility["live_cli_error"]))
        provider = None
        model = None
    if (
        submitted
        and mode in {"auto", "live"}
        and scenario != "coupon-stack"
        and os.environ.get(FIXTURE_LLM_ENV) == "1"
    ):
        raise ValueError(
            "provider-backed modes are disabled while "
            "NXUSKIT_COMMON_SENSE_FIXTURE_LLM=1"
        )
    if submitted and scenario == "synthetic-claims-audit" and mode != "fixture":
        raise ValueError("synthetic claims audit supports Fixture only")
    mechanisms = _selected_items(request.get("mechanisms", []))
    skipped_mechanisms: list[dict[str, str]] = []
    max_repair_attempts = int(request.get("max_repair_attempts", 3))
    if not 1 <= max_repair_attempts <= 10:
        raise ValueError("max_repair_attempts must be between 1 and 10")
    if mechanism_availability is not None:
        mechanisms, skipped_mechanisms = resolve_reasoning_engines(
            scenario, mechanisms, mechanism_availability
        )
    elif scenario == "synthetic-claims-audit":
        mechanisms = [CLAIMS_GUARDRAIL] if CLAIMS_GUARDRAIL in mechanisms else []
    elif mode == "fixture":
        mechanisms = _fixture_guardrails(scenario, mechanisms, mechanism_availability)
    else:
        mechanisms = _compatible_enabled_guardrails(
            scenario, mechanisms, mechanism_availability
        )
    if submitted and not mechanisms:
        raise ValueError(
            "select at least one available Reasoning Engine that applies to this scenario"
        )

    if not submitted:
        return {
            "mode": mode,
            "record": None,
            "effective_guardrails": mechanisms,
            "skipped_mechanisms": skipped_mechanisms,
            "pro_availability": [],
            "requested_provider": str(provider) if provider is not None else None,
            "requested_model": str(model) if model else None,
            "message": "Select inputs, then press Analyze to build the fixture or live record.",
        }

    if mode in {"auto", "live"} and provider is not None:
        if not _enabled(str(provider), provider_availability):
            raise ValueError(f"disabled provider: {provider}")
    if mode == "live" and provider is None:
        raise ValueError("live mode requires a selected enabled provider")
    if scenario == "synthetic-claims-audit":
        emitter = RunEventEmitter(sink=event_sink)
        emitter.emit("run", "started", "Synthetic claims analysis started.")
        emitter.emit(
            "facts",
            "completed",
            "Synthetic claims fixture rows are ready for evaluation.",
            attempt=1,
        )
        engine_component = {
            "kind": "engine",
            "id": CLAIMS_GUARDRAIL,
            "tier": "community",
        }
        emitter.emit(
            "engine",
            "started",
            "Evaluating synthetic claims evidence completeness.",
            attempt=1,
            component=engine_component,
        )
        record = build_claims_reasoning_record()
        emitter.emit(
            "engine",
            "accepted",
            "Claims Audit accepted response attempt 1 for expert review.",
            attempt=1,
            component=engine_component,
        )
        emitter.emit(
            "run",
            "accepted",
            "Synthetic claims evidence was accepted for expert review.",
        )
    else:
        runner_mode = (
            "mock" if mode == "fixture" or scenario == "coupon-stack" else mode
        )
        try:
            with _selected_provider_environment(
                str(provider) if provider is not None else None,
                str(model) if model is not None else None,
            ):
                record = build_reasoning_record(
                    scenario,
                    runner_mode,
                    None,
                    ",".join(mechanisms),
                    max_repair_attempts,
                    event_sink=event_sink,
                    interaction_sink=interaction_sink,
                    provider_id=str(provider) if provider is not None else None,
                    model_id=str(model) if model is not None else None,
                )
        except RuntimeError as exc:
            if mode != "live":
                raise
            if isinstance(exc.__cause__, StructuredJsonError):
                message = (
                    "Live provider responses were received, but their structured "
                    "facts did not satisfy the required contract after repair. Review "
                    "LLM Interactions or choose another model, then try Analyze again."
                )
            else:
                message = (
                    "Live analysis could not validate the provider's structured result. "
                    "Check the selected provider and model, then try Analyze again."
                )
            return {
                "mode": mode,
                "record": None,
                "execution": _execution_summary(scenario, mode, None, provider),
                "effective_guardrails": mechanisms,
                "skipped_mechanisms": skipped_mechanisms,
                "pro_availability": [],
                "requested_provider": str(provider) if provider is not None else None,
                "requested_model": str(model) if model else None,
                "message": message,
            }
    return {
        "mode": mode,
        "record": record,
        "execution": _execution_summary(scenario, mode, record, provider),
        "effective_guardrails": mechanisms,
        "skipped_mechanisms": skipped_mechanisms,
        "pro_availability": [],
        "requested_provider": str(provider) if provider is not None else None,
        "requested_model": str(model) if model else None,
        "message": "Record built after explicit Analyze selection.",
    }


def analyze_request(
    request: Mapping[str, Any] | None = None,
    *,
    submitted: bool | None = None,
    provider_availability: Sequence[Mapping[str, object]] | None = None,
    mechanism_availability: Sequence[Mapping[str, object]] | None = None,
    scenario: str | None = None,
    selected_guardrails: Iterable[str] | str | None = None,
    analyze: bool | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    interaction_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build a record only after Analyze, preserving the phase-one fixture API."""

    if request is not None:
        return _submitted_request(
            request,
            submitted=bool(submitted),
            provider_availability=provider_availability,
            mechanism_availability=mechanism_availability,
            event_sink=event_sink,
            interaction_sink=interaction_sink,
        )

    if scenario is None or selected_guardrails is None or analyze is None:
        raise TypeError(
            "legacy calls require scenario, selected_guardrails, and analyze"
        )

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of: {', '.join(SCENARIOS)}")
    selected = _selected_items(selected_guardrails)
    availability = _pro_availability(selected)
    effective = _effective_guardrails(scenario, selected)
    if not analyze:
        return {
            "mode": "fixture",
            "record": None,
            "effective_guardrails": effective,
            "pro_availability": availability,
            "message": "Select inputs, then press Analyze to build the fixture record.",
        }

    if scenario == "synthetic-claims-audit":
        emitter = RunEventEmitter(sink=event_sink)
        emitter.emit("run", "started", "Synthetic claims analysis started.")
        record = build_claims_reasoning_record()
        emitter.emit(
            "run",
            "accepted",
            "Synthetic claims evidence was accepted for expert review.",
        )
    else:
        record = build_reasoning_record(
            scenario,
            "mock",
            "ce",
            ",".join(effective),
            event_sink=event_sink,
            interaction_sink=interaction_sink,
        )
    return {
        "mode": "fixture",
        "record": record,
        "effective_guardrails": effective,
        "pro_availability": availability,
        "message": "Fixture record built after explicit Analyze selection.",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fixture-first Marimo reasoning-record frontend script."
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="cold-chain")
    parser.add_argument(
        "--guardrails",
        default=",".join(DEFAULT_GUARDRAILS),
        help="Comma-separated Community or explicitly selected Pro mechanisms.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Explicitly build one offline fixture record.",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured output.")
    return parser.parse_args(argv)


def run_script(argv: list[str]) -> int:
    args = parse_args(argv)
    response = analyze_request(
        scenario=args.scenario,
        selected_guardrails=args.guardrails,
        analyze=args.analyze,
    )
    if args.json:
        print(json.dumps(response, indent=2, sort_keys=True))
    else:
        print(response["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(run_script(sys.argv[1:]))
