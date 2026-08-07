"""Deterministic tests for asynchronous provider model discovery."""

from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import Future
from pathlib import Path
from types import ModuleType


MODULE_PATH = Path(__file__).with_name("model_discovery.py")


def load_discovery() -> ModuleType:
    assert MODULE_PATH.is_file(), "missing asynchronous model discovery coordinator"
    spec = importlib.util.spec_from_file_location("model_discovery", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingExecutor:
    def __init__(self, *futures: Future):
        self.futures = iter(futures)
        self.submissions: list[tuple[object, tuple[object, ...]]] = []
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def submit(self, function, *args):
        self.submissions.append((function, args))
        return next(self.futures)

    def shutdown(self, *, wait, cancel_futures):
        self.shutdown_calls.append((wait, cancel_futures))


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def fake_discover(provider):
    raise AssertionError(f"RecordingExecutor must control discovery for {provider}")


def model(module: ModuleType, model_id: str):
    return module.CatalogModel(
        id=model_id,
        name=model_id,
        provider="ollama",
        supports=("chat",),
        context_window=None,
        local=True,
        description=None,
    )


def result(module: ModuleType, state: str, *models):
    message = {
        "ready": "Models ready.",
        "empty": "No models were reported.",
        "failed": "Model discovery was unavailable.",
    }[state]
    return module.CatalogResult("ollama", state, tuple(models), message)


def test_request_returns_loading_without_waiting_for_catalog() -> None:
    """Catches a discovery request that blocks the UI on provider I/O."""

    module = load_discovery()
    future = Future()
    executor = RecordingExecutor(future)
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor
    )

    snapshot = coordinator.request("ollama")

    assert snapshot.state == "loading"
    assert executor.submissions == [(fake_discover, ("ollama",))]
    assert future.done() is False


def test_requesting_both_local_providers_submits_in_parallel() -> None:
    """Catches local discovery that waits for one provider before starting the other."""

    module = load_discovery()
    executor = RecordingExecutor(Future(), Future())
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor
    )

    coordinator.request("ollama")
    coordinator.request("lmstudio")

    assert [args[0] for _, args in executor.submissions] == ["ollama", "lmstudio"]


def test_ready_catalog_is_cached_then_becomes_stale_after_ttl() -> None:
    """Catches unnecessary refreshes or a catalog that never reports staleness."""

    module = load_discovery()
    clock = FakeClock()
    future = Future()
    executor = RecordingExecutor(future)
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor, clock=clock, ttl_seconds=300
    )
    future.set_result(result(module, "ready", model(module, "model-b")))

    coordinator.request("ollama")
    ready = coordinator.poll("ollama")
    cached = coordinator.request("ollama")
    clock.advance(301)
    stale = coordinator.snapshot("ollama")

    assert ready.state == "ready"
    assert cached is ready
    assert len(executor.submissions) == 1
    assert stale.state == "stale"
    assert [item.id for item in stale.models] == ["model-b"]


def test_forced_refresh_rejects_an_older_generation_result() -> None:
    """Catches a late older request overwriting the newest provider catalog."""

    module = load_discovery()
    older = Future()
    newer = Future()
    executor = RecordingExecutor(older, newer)
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor
    )

    first = coordinator.request("ollama")
    second = coordinator.request("ollama", force=True)
    older.set_result(result(module, "ready", model(module, "old-model")))
    while_newer_runs = coordinator.poll("ollama")
    newer.set_result(result(module, "ready", model(module, "new-model")))
    ready = coordinator.poll("ollama")

    assert second.generation == first.generation + 1
    assert while_newer_runs.state == "loading"
    assert [item.id for item in ready.models] == ["new-model"]


def test_failed_refresh_preserves_prior_models_as_stale() -> None:
    """Catches a transient refresh failure erasing a usable cached catalog."""

    module = load_discovery()
    initial = Future()
    refresh = Future()
    executor = RecordingExecutor(initial, refresh)
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor
    )
    initial.set_result(result(module, "ready", model(module, "kept-model")))

    coordinator.request("ollama")
    coordinator.poll("ollama")
    coordinator.request("ollama", force=True)
    refresh.set_result(result(module, "failed"))
    stale = coordinator.poll("ollama")

    assert stale.state == "stale"
    assert [item.id for item in stale.models] == ["kept-model"]
    assert stale.message == "Model discovery was unavailable."


def test_empty_and_unexpected_failure_states_are_safe() -> None:
    """Catches empty catalogs or exceptions being mislabeled or leaking details."""

    module = load_discovery()
    empty_future = Future()
    failed_future = Future()
    executor = RecordingExecutor(empty_future, failed_future)
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor
    )
    empty_future.set_result(result(module, "empty"))
    failed_future.set_exception(RuntimeError("secret provider diagnostic"))

    coordinator.request("ollama")
    empty = coordinator.poll("ollama")
    coordinator.request("lmstudio")
    failed = coordinator.poll("lmstudio")

    assert empty.state == "empty"
    assert empty.models == ()
    assert failed.state == "failed"
    assert failed.message == "Model discovery was unavailable."
    assert "secret" not in failed.message


def test_shutdown_never_touches_an_injected_executor() -> None:
    """Catches coordinator cleanup canceling work owned by another component."""

    module = load_discovery()
    executor = RecordingExecutor(Future())
    coordinator = module.ProviderDiscoveryCoordinator(
        discover=fake_discover, executor=executor
    )

    coordinator.shutdown()

    assert executor.shutdown_calls == []
