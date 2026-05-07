#!/usr/bin/env python3
"""Emit conformance/example_smoke_matrix.json from conformance/examples_manifest.json.

The matrix is consumed by scripts/test-examples.sh --smoke-run. Re-run this script
after adding examples or scenarios; commit the regenerated JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "conformance" / "examples_manifest.json"
OUT = REPO / "conformance" / "example_smoke_matrix.json"

# Go programs that exit non-zero if --scenario is omitted (no default).
GO_REQUIRES_SCENARIO = frozenset(
    {"bayesian-inference", "solver", "bn-solver-clips-pipeline", "llm-solver-hybrid"}
)

# Rust workspaces with multiple [[bin]] targets: preferred smoke binary (manifest example name → bin).
RUST_MULTI_BIN_PREFERRED: dict[str, str] = {
    "clips-basics": "clips_basic",
}

# Examples that typically need a cloud API key (Anthropic/OpenAI) for a full happy-path run.
# Needs LM Studio local server (skip unless SMOKE_INCLUDE_LOCAL_LMSTUDIO=1).
REQUIRES_LOCAL_LMSTUDIO: frozenset[str] = frozenset({"lmstudio"})
# Go examples that log.Fatal when Ollama is down (Rust counterparts often degrade gracefully).
REQUIRES_LOCAL_OLLAMA_GO: frozenset[str] = frozenset(
    {"ollama", "alert-triage", "clips-llm-hybrid"}
)

ANTHROPIC_STYLE_LLM: frozenset[str] = frozenset(
    {
        "basic-chat",
        "streaming",
        "multi-provider",
        "convenience-api",
        "blocking-api",
        "capability-detection",
        "cost-routing",
        "polymorphic",
        "retry-fallback",
        "timeout-config",
        "token-budget",
        "vision",
        "structured-output",
        "cli-assistant",
    }
)

# apps: print help instead of driving full flows (many need LLM or stdin).
APPS_CATEGORY = "apps"

# Pro-tier apps: argv after `--` that exercise the SDK (not `--help`, which exits before FFI).
# Keys: (manifest example name, language).
PRO_APP_ARGV: dict[tuple[str, str], list[str]] = {
    ("arbiter", "rust"): ["--input", "test query", "--max-retries", "1"],
    ("racer", "rust"): ["race", "einstein-riddle"],
    ("racer", "go"): ["race", "einstein-riddle"],
    ("ruler", "rust"): ["generate", "classify adults"],
    ("ruler", "go"): ["generate", "classify adults"],
    ("puzzler", "rust"): ["sudoku", "-p", "easy", "-a", "clips"],
    ("puzzler", "go"): ["sudoku", "-p", "easy", "-a", "clips"],
}

# Pro smoke: no dual token test.  These apps' smoke paths don't hit
# Pro-gated SDK methods, so the entitlement probe would always pass.
# Apps removed from this list now exercise real SDK calls (ClipsProvider,
# ClipsSession, zen_evaluate, LLM providers) in their smoke paths.
NO_ENTITLEMENT_PROBE: frozenset[str] = frozenset({"puzzler", "riffer"})


def load_toml_bins(cargo_toml: Path) -> list[str]:
    if tomllib is None:
        return load_toml_bins_fallback(cargo_toml)
    with open(cargo_toml, "rb") as f:
        data = tomllib.load(f)
    bins: list[str] = []
    for block in data.get("bin") or []:
        if isinstance(block, dict) and "name" in block:
            bins.append(block["name"])
    return bins


def load_toml_bins_fallback(cargo_toml: Path) -> list[str]:
    bins: list[str] = []
    in_bin_block = False
    for raw_line in cargo_toml.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line == "[[bin]]":
            in_bin_block = True
            continue
        if line.startswith("["):
            in_bin_block = False
            continue
        if not in_bin_block:
            continue
        key, sep, value = line.partition("=")
        if sep and key.strip() == "name":
            name = value.strip().strip('"').strip("'")
            if name:
                bins.append(name)
    return bins


def scenario_first(example_dir: Path) -> str | None:
    sd = example_dir / "scenarios"
    if not sd.is_dir():
        return None
    names = sorted(p.name for p in sd.iterdir() if p.is_dir())
    return names[0] if names else None


def go_run_prefix(impl_dir: Path) -> list[str]:
    riffer_main = impl_dir / "cmd" / "riffer" / "main.go"
    if riffer_main.exists():
        return ["go", "run", "-tags", "nxuskit", "./cmd/riffer", "--"]
    if (impl_dir / "cmd" / "main.go").exists():
        return ["go", "run", "-tags", "nxuskit", "./cmd", "--"]
    return ["go", "run", "-tags", "nxuskit", ".", "--"]


def rust_cargo_cmd(
    impl_dir: Path, example_name: str, category: str, example_dir: Path
) -> list[str]:
    cargo_toml = impl_dir / "Cargo.toml"
    cargo = ["cargo", "run", "--quiet"]
    if cargo_toml.is_file():
        bins = load_toml_bins(cargo_toml)
        if len(bins) > 1:
            preferred = RUST_MULTI_BIN_PREFERRED.get(example_name)
            if preferred and preferred in bins:
                cargo += ["--bin", preferred]
            else:
                cargo += ["--bin", sorted(bins)[0]]
    cargo.append("--")
    if category == APPS_CATEGORY:
        key = (example_name, "rust")
        if key in PRO_APP_ARGV:
            return cargo + PRO_APP_ARGV[key]
        return cargo + ["--help"]
    # Scenario crates: clap defaults exist for Rust across solver/bn/zen integrations.
    return cargo


def argv_tail(
    lang: str,
    example_name: str,
    category: str,
    example_dir: Path,
) -> list[str]:
    if example_name == "common-sense-guardrails":
        return ["--scenario", "car-wash", "--mode", "mock", "--stage", "ce"]
    if category == APPS_CATEGORY:
        if lang == "go":
            key = (example_name, "go")
            if key in PRO_APP_ARGV:
                return PRO_APP_ARGV[key]
            return ["-help"]
        if lang == "python":
            return ["--help"]
        return []  # rust app argv from rust_cargo_cmd
    first = scenario_first(example_dir)
    if lang == "go" and example_name in GO_REQUIRES_SCENARIO and first:
        return ["--scenario", first]
    return []


def requires_cloud_llm(example_name: str, tech_tags: list[str]) -> bool:
    if "LLM" not in tech_tags:
        return False
    if example_name in ANTHROPIC_STYLE_LLM:
        return True
    return False


def main() -> int:
    with open(MANIFEST) as f:
        manifest = json.load(f)

    runs: list[dict] = []
    for ex in manifest["examples"]:
        name = ex["name"]
        tier = ex["tier"]
        category = ex["category"]
        tags = list(ex.get("tech_tags") or [])
        impls = ex.get("implementations") or {}
        example_dir = None
        for lang in ("rust", "go", "python", "bash"):
            rel = impls.get(lang)
            if not rel:
                continue
            if lang == "bash" and name != "common-sense-guardrails":
                continue
            impl_dir = REPO / rel
            if not impl_dir.is_dir():
                continue
            if example_dir is None:
                example_dir = impl_dir.parent
            tail = argv_tail(lang, name, category, example_dir)
            entitlement_probe = tier == "pro" and name not in NO_ENTITLEMENT_PROBE
            cloud = requires_cloud_llm(name, tags)
            local_lmstudio = name in REQUIRES_LOCAL_LMSTUDIO
            local_ollama_go = lang == "go" and name in REQUIRES_LOCAL_OLLAMA_GO

            if lang == "rust":
                cmd = rust_cargo_cmd(impl_dir, name, category, example_dir) + (
                    [] if category == APPS_CATEGORY else tail
                )
            elif lang == "go":
                cmd = go_run_prefix(impl_dir) + tail
            elif lang == "bash":
                cmd = ["bash", "main.sh"] + tail
            else:
                cmd = ["python3", "main.py"] + tail

            row = {
                "id": f"{name}|{lang}",
                "example": name,
                "tier": tier,
                "category": category,
                "language": lang,
                "cwd_rel": rel.replace("\\", "/"),
                "command": cmd,
                "entitlement_probe": entitlement_probe,
                "requires_cloud_llm": cloud,
                "requires_local_lmstudio": local_lmstudio,
                "requires_local_ollama_go": local_ollama_go,
            }
            if name == "common-sense-guardrails":
                row.update(
                    {
                        "id": f"{name}|{lang}|ce",
                        "stage": "ce",
                        "stage_tier": "community",
                        "requires_pro": False,
                    }
                )
            runs.append(row)

            if name == "common-sense-guardrails" and lang in {"python", "bash"}:
                runs.append(
                    {
                        "id": f"{name}|{lang}|pro",
                        "example": name,
                        "tier": tier,
                        "category": category,
                        "language": lang,
                        "cwd_rel": rel.replace("\\", "/"),
                        "command": cmd[:-1] + ["pro"],
                        "entitlement_probe": False,
                        "requires_cloud_llm": False,
                        "requires_local_lmstudio": False,
                        "requires_local_ollama_go": False,
                        "stage": "pro",
                        "stage_tier": "pro",
                        "requires_pro": False,
                    }
                )

    out = {
        "$schema": "./harness/example_smoke_matrix.schema.json",
        "version": "1.0.0",
        "description": "Apple Silicon local smoke runs for test-examples.sh --smoke-run",
        "runs": runs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"wrote {OUT} ({len(runs)} runs)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
