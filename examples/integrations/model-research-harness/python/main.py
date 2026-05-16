#!/usr/bin/env python3
"""Python-first model research harness example for nxusKit."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def attach_sdk_python_path() -> None:
    """Prefer the installed SDK Python package when this example is run directly."""

    sdk_dir = os.environ.get("NXUSKIT_SDK_DIR")
    if not sdk_dir and importlib.util.find_spec("nxuskit") is not None:
        return
    base = (
        Path(sdk_dir).expanduser()
        if sdk_dir
        else Path.home() / ".nxuskit" / "sdk" / "current"
    )
    sdk_src = base / "python" / "src"
    if sdk_src.is_dir():
        text = str(sdk_src)
        if text not in sys.path:
            sys.path.insert(0, text)


attach_sdk_python_path()

from harness.config import ConfigError, list_config_paths, load_config  # noqa: E402
from harness.promptfoo_import import import_promptfoo  # noqa: E402
from harness.reports import build_report, write_reports  # noqa: E402
from harness.runner import run_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=str(ROOT / "configs" / "nxuskit-harness-basic.yaml")
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "live", "auto", "dry-run-policy", "import-promptfoo"],
        default="mock",
    )
    parser.add_argument("--import-promptfoo")
    parser.add_argument("--compatibility-report")
    parser.add_argument("--allow-code", action="store_true")
    parser.add_argument("--promptfoo-native-reference", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument(
        "--only-test",
        action="append",
        default=[],
        help="Run only matching test id(s). Accepts comma-separated values and may be repeated.",
    )
    parser.add_argument(
        "--exclude-test",
        action="append",
        default=[],
        help="Skip matching test id(s). Accepts comma-separated values and may be repeated.",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Allow configs to execute explicit external-command adapters.",
    )
    parser.add_argument(
        "--allow-lifecycle-mutations",
        action="store_true",
        help="Allow external-command adapters marked as lifecycle mutations to run.",
    )
    parser.add_argument(
        "--output-dir", default=str(ROOT / ".tmp" / "model-research-harness")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list-configs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_configs:
        for path in list_config_paths(ROOT):
            print(path.relative_to(ROOT))
        return 0

    compatibility = None
    try:
        if args.import_promptfoo:
            config, compatibility = import_promptfoo(
                Path(args.import_promptfoo),
                allow_code=args.allow_code,
                native_reference=args.promptfoo_native_reference,
            )
            if compatibility and args.compatibility_report:
                write_json(Path(args.compatibility_report), compatibility)
            if config is None:
                if args.json:
                    print(json.dumps({"compatibility_report": compatibility}, indent=2))
                else:
                    print("Promptfoo import requires an explicit trust/reference flag.")
                return 0
        else:
            config_path = Path(args.config)
            config = load_config(config_path)
            config["_config_dir"] = str(config_path.resolve().parent)
        filter_tests(config, include=args.only_test, exclude=args.exclude_test)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    mode = "mock" if args.mode in {"dry-run-policy", "import-promptfoo"} else args.mode
    output_dir = Path(args.output_dir)
    results, bayesian, recommendations, truth = run_config(
        config,
        mode=mode,
        provider_override=args.provider,
        model_override=args.model,
        output_dir=output_dir,
        allow_external_commands=args.allow_external,
        allow_lifecycle_mutations=args.allow_lifecycle_mutations,
    )
    report = build_report(
        config, results, bayesian, recommendations, truth, compatibility
    )
    if not args.dry_run:
        write_reports(report, output_dir)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"config: {report['config_id']}")
        print(f"status: {report['final_status']}")
        print(f"results: {len(report['results'])}")
        print(f"summary: {output_dir / 'summary.md'}")
    return 0 if report["final_status"] == "pass" else 1


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def filter_tests(config: dict, *, include: list[str], exclude: list[str]) -> None:
    includes = split_filters(include)
    excludes = split_filters(exclude)
    if not includes and not excludes:
        return
    tests = config.get("tests") or []
    selected = []
    for test in tests:
        test_id = str(test.get("id", ""))
        if includes and test_id not in includes:
            continue
        if test_id in excludes:
            continue
        selected.append(test)
    if not selected:
        raise ConfigError("test filter selected no tests")
    config["tests"] = selected


def split_filters(values: list[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        out.update(item.strip() for item in value.split(",") if item.strip())
    return out


if __name__ == "__main__":
    raise SystemExit(main())
