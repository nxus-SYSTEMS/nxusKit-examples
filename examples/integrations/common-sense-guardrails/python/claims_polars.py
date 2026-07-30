"""Optional Polars projections for bounded synthetic administrative rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _polars() -> Any:
    try:
        import polars as pl
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install the pinned reasoning-lab dependencies before selecting Polars views."
        ) from exc
    return pl


def claims_lazy_summary(path: Path) -> dict[str, Any]:
    """Show a lazy scan, a small synthetic reference join, and streaming collection."""

    pl = _polars()
    source = pl.scan_csv(path).select(
        [
            "line_key",
            "claim_key",
            "service_ref",
            "provider_ref",
            "recorded_amount_cents",
            "synthetic",
        ]
    )
    provider_dimension = pl.LazyFrame(
        {
            "provider_ref": [f"generated-provider-{index:03d}" for index in range(23)],
            "synthetic_provider_group": [f"group-{index % 4}" for index in range(23)],
        }
    )
    lazy = (
        source.filter(pl.col("synthetic").cast(pl.Boolean, strict=True))
        .join(provider_dimension, on="provider_ref", how="left")
        .select(
            "line_key",
            "claim_key",
            "service_ref",
            "provider_ref",
            "synthetic_provider_group",
            "recorded_amount_cents",
        )
    )
    query_plan = lazy.explain(optimized=True)
    materialized = lazy.collect(engine="streaming")
    aggregates = (
        lazy.group_by("synthetic_provider_group")
        .agg(pl.len().alias("line_count"))
        .collect(engine="streaming")
    )
    return {
        "row_count": materialized.height,
        "query_plan": query_plan,
        "streaming_engine": "streaming",
        "materialized": materialized,
        "provider_aggregates": aggregates,
    }


def claims_observational_sql(frame: Any) -> dict[str, int]:
    """Count already-materialized synthetic rows through Polars SQLContext."""

    pl = _polars()
    context = pl.SQLContext(register_globals=False)
    context.register("synthetic_claim_lines", frame)
    result = context.execute(
        "SELECT COUNT(*) AS row_count FROM synthetic_claim_lines", eager=True
    )
    return {"row_count": int(result.item(0, 0))}
