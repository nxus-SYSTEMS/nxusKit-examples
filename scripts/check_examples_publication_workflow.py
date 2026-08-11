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
VALIDATION_STEP = "Materialize validation export"
RELEASE_VALIDATION_STEP = "Release contract assertion — exported workflow"
BOUNDARY_STEP = "Boundary assertion — forbidden dirs absent from validation export"
PUBLISH_EXPORT_STEP = "Materialize pristine publish export"
PUBLISH_STEP = "Merge into public repo"
VALIDATION_EXPORT_ROOT = "/tmp/nxusKit-examples-validation-export"
PUBLISH_EXPORT_ROOT = "/tmp/nxusKit-examples-publish-export"
VALIDATION_COMMANDS = (
    "set -euo pipefail",
    f"VALIDATION_EXPORT={VALIDATION_EXPORT_ROOT}",
    'rm -rf "$VALIDATION_EXPORT"',
    'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA"',
    'python3 scripts/examples_publication_tree.py materialize-public-export --repo . --source-ref "$GITHUB_SHA" --output "$VALIDATION_EXPORT"',
    'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA" --filter-export "$VALIDATION_EXPORT"',
    'python3 scripts/examples_publication_tree.py attest-public-export --export-root "$VALIDATION_EXPORT"',
)
PUBLISH_EXPORT_COMMANDS = (
    "set -euo pipefail",
    f"VALIDATION_EXPORT={VALIDATION_EXPORT_ROOT}",
    f"PUBLISH_EXPORT={PUBLISH_EXPORT_ROOT}",
    'rm -rf "$VALIDATION_EXPORT" "$PUBLISH_EXPORT"',
    'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA"',
    'python3 scripts/examples_publication_tree.py materialize-public-export --repo . --source-ref "$GITHUB_SHA" --output "$PUBLISH_EXPORT"',
    'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA" --filter-export "$PUBLISH_EXPORT"',
    'EXPORT_RECEIPT=$(python3 scripts/examples_publication_tree.py attest-public-export --export-root "$PUBLISH_EXPORT")',
    'EXPORT_TREE_SHA256=$(python3 -c \'import json, sys; print(json.load(sys.stdin)["export_tree_sha256"])\' <<<"$EXPORT_RECEIPT")',
    'echo "export_tree_sha256=$EXPORT_TREE_SHA256" >> "$GITHUB_OUTPUT"',
)
FORCE_STAGE_COMMAND = "git add --all --force"
STAGED_ATTESTATION_COMMAND = (
    'python3 "$GITHUB_WORKSPACE/scripts/examples_publication_tree.py" '
    'attest-staged-export --repo . --export-root "$PUBLISH_EXPORT" '
    "--expected-export-sha256 "
    '"${{ steps.publish-export.outputs.export_tree_sha256 }}"'
)
PUBLISH_RSYNC_COMMANDS = (
    "rsync -a --delete \\",
    "--exclude='.git' \\",
    '"$PUBLISH_EXPORT/" /tmp/nxusKit-examples-public/',
)
PUBLISH_COMMANDS = (
    "set -eu -o pipefail",
    f"PUBLISH_EXPORT={PUBLISH_EXPORT_ROOT}",
    'if [[ -z "${PUBLIC_REPO_URL:-}" ]] || [[ -z "${PUBLIC_REPO_TOKEN:-}" ]]; then',
    'echo "::notice::Public repo secrets not configured — skipping push."',
    'echo "Configure EXAMPLES_PUBLIC_REPO_URL and EXAMPLES_PUBLIC_REPO_TOKEN to enable."',
    "exit 0",
    "fi",
    'REMOTE_URL="https://x-access-token:${PUBLIC_REPO_TOKEN}@${PUBLIC_REPO_URL}"',
    'git clone --depth=1 "$REMOTE_URL" /tmp/nxusKit-examples-public',
    "cd /tmp/nxusKit-examples-public",
    *PUBLISH_RSYNC_COMMANDS,
    FORCE_STAGE_COMMAND,
    STAGED_ATTESTATION_COMMAND,
    "if git diff --cached --quiet; then",
    'echo "No changes to publish."',
    "exit 0",
    "fi",
    'git -c user.name="nxusKit Mirror" \\',
    '-c user.email="mirror@nxuskit.local" \\',
    'commit -m "$COMMIT_MSG"',
    "git push origin main",
    'echo "Successfully pushed to public repository."',
)
GIT_ADD_PATTERN = re.compile(r"(?:^|\b)git\s+add(?:\s|$)")
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
    step_id: str | None
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
        step_id: str | None = None
        run_index: int | None = None
        run_indent = 0
        for index in range(start + 1, end):
            id_match = re.match(r"^\s*id:\s*(.*?)\s*$", lines[index])
            if id_match:
                step_id = _unquote(id_match.group(1))
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
        steps.append(
            RunStep(
                name=name,
                step_id=step_id,
                commands=tuple(commands),
                order=order,
            )
        )
    return tuple(steps)


def _contains_prohibited_copy(command: str) -> bool:
    return any(
        pattern.search(command) is not None for pattern in PROHIBITED_COPY_PATTERNS
    )


def _references_variable(command: str, name: str) -> bool:
    return re.search(rf"\${re.escape(name)}(?![A-Za-z0-9_])", command) is not None


def validate_private_workflow(text: str) -> list[str]:
    """Return publication workflow contract violations."""

    errors: list[str] = []
    steps = _run_steps(text)
    required_names = (
        VALIDATION_STEP,
        RELEASE_VALIDATION_STEP,
        BOUNDARY_STEP,
        PUBLISH_EXPORT_STEP,
        PUBLISH_STEP,
    )
    matched = {
        name: tuple(step for step in steps if step.name == name)
        for name in required_names
    }
    for name, named_steps in matched.items():
        if len(named_steps) != 1:
            errors.append(f"expected exactly one {name!r} run step")
    if errors:
        return errors

    validation_step = matched[VALIDATION_STEP][0]
    release_step = matched[RELEASE_VALIDATION_STEP][0]
    boundary_step = matched[BOUNDARY_STEP][0]
    publish_export_step = matched[PUBLISH_EXPORT_STEP][0]
    publish_step = matched[PUBLISH_STEP][0]

    if not (
        validation_step.order
        < release_step.order
        < boundary_step.order
        < publish_export_step.order
        < publish_step.order
    ):
        errors.append("publication validation and publish steps are out of order")
    if publish_step.order != publish_export_step.order + 1:
        errors.append("pristine publish export must be immediately followed by merge")

    if validation_step.commands != VALIDATION_COMMANDS:
        errors.append(
            f"{VALIDATION_STEP!r} commands must match the exact tracked-only contract"
        )
    for command in validation_step.commands:
        if _contains_prohibited_copy(command):
            errors.append(
                f"prohibited ambient copy command in validation step: {command}"
            )

    required_release_commands = (
        "set -eu -o pipefail",
        f"VALIDATION_EXPORT={VALIDATION_EXPORT_ROOT}",
        "export PYTHONDONTWRITEBYTECODE=1",
        'cd "$VALIDATION_EXPORT"',
    )
    for command in required_release_commands:
        if release_step.commands.count(command) != 1:
            errors.append(
                f"{RELEASE_VALIDATION_STEP!r} must contain exactly one {command!r}"
            )
    if all(command in release_step.commands for command in required_release_commands):
        positions = tuple(
            release_step.commands.index(command)
            for command in required_release_commands
        )
        if positions != tuple(sorted(positions)):
            errors.append(
                f"{RELEASE_VALIDATION_STEP!r} defensive commands are out of order"
            )

    if boundary_step.commands[:2] != (
        "set -eu -o pipefail",
        f"VALIDATION_EXPORT={VALIDATION_EXPORT_ROOT}",
    ):
        errors.append(f"{BOUNDARY_STEP!r} must use only the validation export root")

    if publish_export_step.step_id != "publish-export":
        errors.append(f"{PUBLISH_EXPORT_STEP!r} must use id 'publish-export'")
    if publish_export_step.commands != PUBLISH_EXPORT_COMMANDS:
        errors.append(
            f"{PUBLISH_EXPORT_STEP!r} commands must match the exact pristine contract"
        )
    if publish_step.commands != PUBLISH_COMMANDS:
        errors.append(f"{PUBLISH_STEP!r} commands must match the exact push contract")

    legacy_root = "/tmp/nxusKit-examples-export"
    for step in steps:
        for command in step.commands:
            if _references_variable(command, "EXPORT") or legacy_root in command:
                errors.append(f"step {step.name!r} references the retired export root")
            if step.name not in (PUBLISH_EXPORT_STEP, PUBLISH_STEP) and (
                _references_variable(command, "PUBLISH_EXPORT")
                or PUBLISH_EXPORT_ROOT in command
            ):
                errors.append(
                    f"step {step.name!r} references the pristine publish export"
                )
    for command in publish_step.commands:
        if (
            _references_variable(command, "VALIDATION_EXPORT")
            or VALIDATION_EXPORT_ROOT in command
        ):
            errors.append(f"{PUBLISH_STEP!r} references the validation export")

    add_commands = tuple(
        command for command in publish_step.commands if GIT_ADD_PATTERN.search(command)
    )
    if add_commands != (FORCE_STAGE_COMMAND,):
        errors.append(f"{PUBLISH_STEP!r} must use exactly one force-stage command")

    rsync_indexes: list[int] = []
    for command in PUBLISH_RSYNC_COMMANDS:
        try:
            rsync_indexes.append(publish_step.commands.index(command))
        except ValueError:
            errors.append(f"{PUBLISH_STEP!r} must rsync only the pristine export")
            break
    else:
        if rsync_indexes != list(
            range(rsync_indexes[0], rsync_indexes[0] + len(PUBLISH_RSYNC_COMMANDS))
        ):
            errors.append(f"{PUBLISH_STEP!r} pristine rsync commands must be adjacent")

    python_commands = tuple(
        command for command in publish_step.commands if command.startswith("python3 ")
    )
    if python_commands != (STAGED_ATTESTATION_COMMAND,):
        errors.append(f"{PUBLISH_STEP!r} has an alternate Python execution path")

    allowed_publish_references = {
        f"PUBLISH_EXPORT={PUBLISH_EXPORT_ROOT}",
        PUBLISH_RSYNC_COMMANDS[-1],
        STAGED_ATTESTATION_COMMAND,
    }
    for command in publish_step.commands:
        if (
            _references_variable(command, "PUBLISH_EXPORT")
            or PUBLISH_EXPORT_ROOT in command
        ) and command not in allowed_publish_references:
            errors.append(
                f"{PUBLISH_STEP!r} has an unauthorized publish-export command: {command}"
            )

    try:
        force_index = publish_step.commands.index(FORCE_STAGE_COMMAND)
        attest_index = publish_step.commands.index(STAGED_ATTESTATION_COMMAND)
    except ValueError:
        errors.append(f"{PUBLISH_STEP!r} must attest the exact staged export")
    else:
        if attest_index != force_index + 1:
            errors.append(
                f"{PUBLISH_STEP!r} must attest immediately after force-staging"
            )
    return errors


def _safe_fixture() -> str:
    validation_body = "\n".join(
        f"          {command}" for command in VALIDATION_COMMANDS
    )
    release_body = "\n".join(
        f"          {command}"
        for command in (
            "set -eu -o pipefail",
            f"VALIDATION_EXPORT={VALIDATION_EXPORT_ROOT}",
            "export PYTHONDONTWRITEBYTECODE=1",
            "(",
            'cd "$VALIDATION_EXPORT"',
            "python3 scripts/examples_publication_tree.py self-test",
            ")",
        )
    )
    boundary_body = "\n".join(
        f"          {command}"
        for command in (
            "set -eu -o pipefail",
            f"VALIDATION_EXPORT={VALIDATION_EXPORT_ROOT}",
            'test -f "$VALIDATION_EXPORT/NOTICE"',
        )
    )
    publish_export_body = "\n".join(
        f"          {command}" for command in PUBLISH_EXPORT_COMMANDS
    )
    publish_body = "\n".join(f"          {command}" for command in PUBLISH_COMMANDS)
    return f"""name: Safe publication fixture
jobs:
  mirror:
    steps:
      - name: Materialize validation export
        run: |
{validation_body}
      - name: Release contract assertion — exported workflow
        run: |
{release_body}
      - name: Boundary assertion — forbidden dirs absent from validation export
        run: |
{boundary_body}
      - name: Materialize pristine publish export
        id: publish-export
        run: |
{publish_export_body}
      - name: Merge into public repo
        run: |
{publish_body}
"""


def run_self_test() -> dict[str, object]:
    safe = _safe_fixture()
    if validate_private_workflow(safe):
        raise RuntimeError("safe publication workflow fixture was rejected")
    for command in VALIDATION_COMMANDS[2:]:
        mutated = safe.replace(f"          {command}\n", "", 1)
        if not validate_private_workflow(mutated):
            raise RuntimeError(f"missing command mutation was accepted: {command}")
    if not validate_private_workflow(safe.replace('"$GITHUB_SHA"', '"$OTHER_SHA"', 1)):
        raise RuntimeError("non-exact source ref mutation was accepted")
    for command in (
        "export PYTHONDONTWRITEBYTECODE=1",
        'rm -rf "$VALIDATION_EXPORT" "$PUBLISH_EXPORT"',
        'echo "export_tree_sha256=$EXPORT_TREE_SHA256" >> "$GITHUB_OUTPUT"',
        FORCE_STAGE_COMMAND,
        STAGED_ATTESTATION_COMMAND,
    ):
        mutated = safe.replace(f"          {command}\n", "", 1)
        if not validate_private_workflow(mutated):
            raise RuntimeError(
                f"missing immutable-export command was accepted: {command}"
            )
    for old, new in (
        ("$VALIDATION_EXPORT", "$PUBLISH_EXPORT"),
        (
            "rsync -a --delete \\\n          --exclude='.git' \\\n          \"$PUBLISH_EXPORT/\"",
            "rsync -a --delete \\\n          --exclude='.git' \\\n          \"$VALIDATION_EXPORT/\"",
        ),
    ):
        if not validate_private_workflow(safe.replace(old, new, 1)):
            raise RuntimeError(f"export-root mutation was accepted: {old}")
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
                required_count = 5
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
