#!/usr/bin/env python3
"""Validate the exact tracked-only Examples publication workflow contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CRITICAL_STEP = "Export approved tracked content"
REQUIRED_COMMANDS = (
    "set -euo pipefail",
    "EXPORT=/tmp/nxusKit-examples-export",
    'rm -rf "$EXPORT"',
    'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA"',
    'python3 scripts/examples_publication_tree.py materialize-public-export --repo . --source-ref "$GITHUB_SHA" --output "$EXPORT"',
    'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA" --filter-export "$EXPORT"',
    'python3 scripts/examples_publication_tree.py attest-public-export --export-root "$EXPORT"',
)
PROHIBITED_COPY_PATTERNS = (
    re.compile(r"(?:^|[;&|]\s*)cp\s+(?:-[^ ]*\s+)*(?:-a|-R)(?:\s|$)"),
    re.compile(r"(?:^|[;&|]\s*)rsync(?:\s|$)"),
    re.compile(r"shutil\.copytree"),
    re.compile(r"(?:^|[;&|]\s*)tar(?:\s|$)"),
    re.compile(r"git\s+archive"),
)
TREE_SELF_TEST = "python3 scripts/examples_publication_tree.py self-test"
TREE_UNIT_TESTS = "python3 scripts/test_examples_publication_tree.py"
GENERATOR_SELF_TEST = (
    "python3 scripts/generate-examples-publication-selection.py --self-test"
)
GENERATOR_CHECK = "python3 scripts/generate-examples-publication-selection.py --check"
PRIVATE_LAYOUT_CHECK = "python3 scripts/check_examples_publication_workflow.py --self-test --layout private"
PUBLIC_LAYOUT_CHECK = (
    "python3 scripts/check_examples_publication_workflow.py --self-test --layout public"
)
EXPORT_ATTESTATION = (
    "python3 scripts/examples_publication_tree.py attest-public-export --export-root ."
)
PRIVATE_WIRING_REQUIREMENTS = {
    "pre_pr": (
        TREE_SELF_TEST,
        TREE_UNIT_TESTS,
        GENERATOR_SELF_TEST,
        GENERATOR_CHECK,
        PRIVATE_LAYOUT_CHECK,
    ),
    "private_ci": (
        TREE_SELF_TEST,
        TREE_UNIT_TESTS,
        GENERATOR_SELF_TEST,
        GENERATOR_CHECK,
        PRIVATE_LAYOUT_CHECK,
    ),
    "public_ci": (
        TREE_SELF_TEST,
        TREE_UNIT_TESTS,
        GENERATOR_SELF_TEST,
        GENERATOR_CHECK,
        PUBLIC_LAYOUT_CHECK,
    ),
    "mirror": (
        TREE_SELF_TEST,
        TREE_UNIT_TESTS,
        GENERATOR_SELF_TEST,
        GENERATOR_CHECK,
        EXPORT_ATTESTATION,
        PUBLIC_LAYOUT_CHECK,
    ),
}
PUBLIC_WIRING_REQUIREMENTS = {
    "public_ci": (
        TREE_SELF_TEST,
        TREE_UNIT_TESTS,
        GENERATOR_SELF_TEST,
        GENERATOR_CHECK,
        PUBLIC_LAYOUT_CHECK,
    ),
}
PRIVATE_INTEGRATION_PATHS = {
    "pre_pr": "scripts/pre-pr-check.sh",
    "private_ci": ".github/workflows/ci.yml",
    "public_ci": ".github/workflows-public/ci.yml",
    "mirror": ".github/workflows/publish-to-public.yml",
}
PUBLIC_INTEGRATION_PATHS = {
    "public_ci": ".github/workflows/ci.yml",
}


@dataclass(frozen=True)
class RunStep:
    name: str
    commands: tuple[str, ...]
    order: int


def _unquote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "'\"":
        return stripped[1:-1]
    return stripped


def _run_steps(text: str) -> tuple[RunStep, ...]:
    lines = text.splitlines()
    starts: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)-\s+name:\s*(.*?)\s*$", line)
        if match:
            starts.append((index, len(match.group(1)), _unquote(match.group(2))))

    steps: list[RunStep] = []
    for order, (start, indent, name) in enumerate(starts):
        end = len(lines)
        for later_start, later_indent, _later_name in starts[order + 1 :]:
            if later_indent == indent:
                end = later_start
                break
        run_index: int | None = None
        run_indent = 0
        for index in range(start + 1, end):
            match = re.match(r"^(\s*)run:\s*\|[-+]?\s*$", lines[index])
            if match:
                run_index = index
                run_indent = len(match.group(1))
                break
        if run_index is None:
            continue
        commands: list[str] = []
        for line in lines[run_index + 1 : end]:
            if line.strip() and len(line) - len(line.lstrip()) <= run_indent:
                break
            command = line.strip()
            if command and not command.startswith("#"):
                commands.append(command)
        steps.append(RunStep(name=name, commands=tuple(commands), order=order))
    return tuple(steps)


def _contains_prohibited_copy(command: str) -> bool:
    return any(
        pattern.search(command) is not None for pattern in PROHIBITED_COPY_PATTERNS
    )


def validate_private_workflow(text: str) -> list[str]:
    """Return publication workflow contract violations."""

    errors: list[str] = []
    steps = _run_steps(text)
    critical = [step for step in steps if step.name == CRITICAL_STEP]
    if len(critical) != 1:
        errors.append(f"expected exactly one {CRITICAL_STEP!r} run step")
        return errors

    export_step = critical[0]
    if export_step.commands != REQUIRED_COMMANDS:
        errors.append(
            f"{CRITICAL_STEP!r} commands must match the exact tracked-only contract"
        )
    for command in export_step.commands:
        if _contains_prohibited_copy(command):
            errors.append(f"prohibited ambient copy command in export step: {command}")

    for step in steps:
        if step.order >= export_step.order or step.name == CRITICAL_STEP:
            continue
        for command in step.commands:
            if "$EXPORT" in command or "/tmp/nxusKit-examples-export" in command:
                errors.append(
                    f"pre-attestation step {step.name!r} references the export root"
                )
            if _contains_prohibited_copy(command):
                errors.append(
                    f"pre-attestation step {step.name!r} uses an ambient copy command"
                )
    return errors


def _safe_fixture() -> str:
    body = "\n".join(f"          {command}" for command in REQUIRED_COMMANDS)
    return f"""name: Safe publication fixture
jobs:
  mirror:
    steps:
      - name: Export approved tracked content
        run: |
{body}
"""


def run_self_test() -> dict[str, object]:
    safe = _safe_fixture()
    if validate_private_workflow(safe):
        raise RuntimeError("safe publication workflow fixture was rejected")
    for command in REQUIRED_COMMANDS[2:]:
        mutated = safe.replace(f"          {command}\n", "", 1)
        if not validate_private_workflow(mutated):
            raise RuntimeError(f"missing command mutation was accepted: {command}")
    if not validate_private_workflow(safe.replace('"$GITHUB_SHA"', '"$OTHER_SHA"', 1)):
        raise RuntimeError("non-exact source ref mutation was accepted")
    return {"ok": True, "workflow_contract_mutations_rejected": True}


def wiring_requirements(layout: str) -> dict[str, tuple[str, ...]]:
    if layout == "private":
        return PRIVATE_WIRING_REQUIREMENTS
    if layout == "public":
        return PUBLIC_WIRING_REQUIREMENTS
    raise ValueError(f"unsupported layout: {layout}")


def integration_documents(repo: Path, layout: str) -> dict[str, str]:
    paths = (
        PRIVATE_INTEGRATION_PATHS
        if layout == "private"
        else PUBLIC_INTEGRATION_PATHS
        if layout == "public"
        else None
    )
    if paths is None:
        raise ValueError(f"unsupported layout: {layout}")
    documents: dict[str, str] = {}
    for label, relative in paths.items():
        path = repo / relative
        if not path.is_file():
            documents[label] = ""
        else:
            documents[label] = path.read_text(encoding="utf-8")
    return documents


def _executable_occurrences(text: str, command: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and command in line
    )


def validate_integration_documents(documents: dict[str, str], layout: str) -> list[str]:
    errors: list[str] = []
    for label, commands in wiring_requirements(layout).items():
        text = documents.get(label, "")
        for command in commands:
            required_count = 1
            if label == "mirror" and command == GENERATOR_CHECK:
                required_count = 3
            if _executable_occurrences(text, command) < required_count:
                errors.append(f"{label}: missing required command: {command}")
    return errors


def validate_layout(repo: Path, layout: str) -> list[str]:
    errors: list[str] = []
    private_workflow = repo / ".github" / "workflows" / "publish-to-public.yml"
    if layout == "private":
        if not private_workflow.is_file():
            return ["private publication workflow is missing"]
        errors.extend(
            validate_private_workflow(private_workflow.read_text(encoding="utf-8"))
        )
    else:
        forbidden = (
            private_workflow,
            repo / ".github" / "workflows" / "publish-to-docs.yml",
            repo / ".github" / "workflows-public",
        )
        for path in forbidden:
            if path.exists():
                errors.append(
                    f"public layout contains private path: {path.relative_to(repo)}"
                )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", required=True)
    parser.add_argument("--layout", choices=("private", "public"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        receipt = run_self_test()
        errors = validate_layout(REPO, args.layout)
        errors.extend(
            validate_integration_documents(
                integration_documents(REPO, args.layout), args.layout
            )
        )
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 2
        receipt["layout"] = args.layout
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
