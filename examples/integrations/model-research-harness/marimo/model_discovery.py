"""Asynchronous, generation-safe model discovery for Model Research."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Literal

from model_catalog import CatalogModel, CatalogResult, discover_provider_models


DiscoveryState = Literal["idle", "loading", "ready", "empty", "stale", "failed"]


@dataclass(frozen=True)
class DiscoverySnapshot:
    provider: str
    state: DiscoveryState
    models: tuple[CatalogModel, ...]
    generation: int
    requested_at: float | None
    completed_at: float | None
    message: str


def _idle(provider: str) -> DiscoverySnapshot:
    return DiscoverySnapshot(
        provider, "idle", (), 0, None, None, "Model discovery has not started."
    )


class ProviderDiscoveryCoordinator:
    """Coordinate bounded background catalog reads without evaluation effects."""

    def __init__(
        self,
        discover: Callable[[str], CatalogResult] = discover_provider_models,
        *,
        ttl_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        executor: Executor | None = None,
    ) -> None:
        self._discover = discover
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="research-model-catalog"
        )
        self._snapshots: dict[str, DiscoverySnapshot] = {}
        self._pending: dict[str, tuple[int, Future[CatalogResult]]] = {}

    def request(self, provider: str, *, force: bool = False) -> DiscoverySnapshot:
        current = self.snapshot(provider)
        if not force and current.state in {"loading", "ready", "empty"}:
            return current
        generation = current.generation + 1
        loading = DiscoverySnapshot(
            provider,
            "loading",
            current.models,
            generation,
            self._clock(),
            current.completed_at,
            "Loading models through released nxusKit.",
        )
        self._snapshots[provider] = loading
        self._pending[provider] = (
            generation,
            self._executor.submit(self._discover, provider),
        )
        return loading

    def poll(self, provider: str) -> DiscoverySnapshot:
        pending = self._pending.get(provider)
        if pending is None:
            return self.snapshot(provider)
        generation, future = pending
        current = self._snapshots.get(provider, _idle(provider))
        if generation != current.generation or not future.done():
            return current
        self._pending.pop(provider, None)
        try:
            result = future.result()
        except Exception:
            result = CatalogResult(
                provider, "failed", (), "Model discovery was unavailable."
            )
        completed_at = self._clock()
        if result.provider != provider:
            result = CatalogResult(
                provider, "failed", (), "Model discovery was unavailable."
            )
        if result.state == "ready":
            snapshot = DiscoverySnapshot(
                provider,
                "ready",
                tuple(sorted(result.models, key=lambda item: item.name.casefold())),
                generation,
                current.requested_at,
                completed_at,
                result.message,
            )
        elif result.state == "empty":
            snapshot = DiscoverySnapshot(
                provider,
                "empty",
                (),
                generation,
                current.requested_at,
                completed_at,
                result.message,
            )
        elif current.models:
            snapshot = DiscoverySnapshot(
                provider,
                "stale",
                current.models,
                generation,
                current.requested_at,
                completed_at,
                result.message,
            )
        else:
            snapshot = DiscoverySnapshot(
                provider,
                "failed",
                (),
                generation,
                current.requested_at,
                completed_at,
                "Model discovery was unavailable.",
            )
        self._snapshots[provider] = snapshot
        return snapshot

    def snapshot(self, provider: str) -> DiscoverySnapshot:
        current = self._snapshots.get(provider, _idle(provider))
        if (
            current.state in {"ready", "empty"}
            and current.completed_at is not None
            and self._clock() - current.completed_at > self._ttl_seconds
        ):
            current = replace(
                current, state="stale", message="The cached model catalog is stale."
            )
            self._snapshots[provider] = current
        return current

    def shutdown(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
