#!/usr/bin/env python3
"""Fail closed when the exported public Release workflow can auto-publish."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CONFIRMATION_TOKEN = "CONFIRM_RELEASE"
MAIN_REF = "refs/heads/main"
DEFAULT_WORKFLOW = Path(".github/workflows-public/release.yml")


def indented_block(text: str, key: str, indent: int) -> str | None:
    """Return the YAML indentation block for an unquoted mapping key."""

    lines = text.splitlines()
    key_pattern = re.compile(rf"^ {{%d}}%s:\s*(?:#.*)?$" % (indent, re.escape(key)))
    start = next((index for index, line in enumerate(lines) if key_pattern.match(line)), None)
    if start is None:
        return None

    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
            break
        block.append(line)
    return "\n".join(block)


def mapping_keys(block: str, indent: int) -> list[str]:
    pattern = re.compile(rf"^ {{%d}}([A-Za-z0-9_-]+):" % indent)
    return [match.group(1) for line in block.splitlines() if (match := pattern.match(line))]


def validate(workflow: str) -> list[str]:
    """Return public-release gate violations for the workflow source."""

    errors: list[str] = []
    triggers = indented_block(workflow, "on", 0)
    if triggers is None:
        errors.append("workflow must declare an unquoted top-level on: mapping")
    elif mapping_keys(triggers, 2) != ["workflow_dispatch"]:
        errors.append("workflow triggers must be workflow_dispatch only; push-triggered releases are forbidden")

    dispatch = indented_block(workflow, "workflow_dispatch", 2)
    inputs = indented_block(workflow, "inputs", 4) if dispatch is not None else None
    confirmation = indented_block(workflow, "confirm_release", 6) if inputs is not None else None
    if confirmation is None:
        errors.append("workflow_dispatch must require the confirm_release input")
    else:
        if not re.search(r"^ {8}required: true\s*$", confirmation, flags=re.MULTILINE):
            errors.append("confirm_release must be required")
        if not re.search(r"^ {8}type: string\s*$", confirmation, flags=re.MULTILINE):
            errors.append("confirm_release must be a string input")
        if CONFIRMATION_TOKEN not in confirmation:
            errors.append("confirm_release must document the fixed confirmation token")

    gate_marker = "- name: Validate manual release gate"
    checkout_marker = "- uses: actions/checkout@v6"
    metadata_marker = "- name: Read SDK version and stats"
    release_marker = "- name: Create or update release"
    gate_index = workflow.find(gate_marker)
    checkout_index = workflow.find(checkout_marker)
    metadata_index = workflow.find(metadata_marker)
    release_index = workflow.find(release_marker)
    if gate_index < 0 or checkout_index < 0 or metadata_index < 0 or release_index < 0:
        errors.append("release job must retain gate, checkout, metadata, and release steps")
    elif not gate_index < checkout_index < metadata_index < release_index:
        errors.append("manual gate must run before checkout, metadata, and release API steps")
    else:
        gate = workflow[gate_index:checkout_index]
        required_gate_fragments = (
            "RELEASE_CONFIRMATION: ${{ inputs.confirm_release }}",
            "SELECTED_REF: ${{ github.ref }}",
            f'"$RELEASE_CONFIRMATION" != "{CONFIRMATION_TOKEN}"',
            f'"$SELECTED_REF" != "{MAIN_REF}"',
            "exit 1",
        )
        for fragment in required_gate_fragments:
            if fragment not in gate:
                errors.append(f"manual gate must fail closed with {fragment!r}")

    if "gh release view \"$TAG\"" not in workflow:
        errors.append("release idempotency check must remain present")
    if "gh release create \"$TAG\"" not in workflow:
        errors.append("release creation command must remain present behind the manual gate")

    top_permissions = indented_block(workflow, "permissions", 0)
    release_job = indented_block(workflow, "release", 2)
    if top_permissions is not None and "contents: write" in top_permissions:
        errors.append("contents: write must be scoped to the explicitly confirmed release job")
    if release_job is None or "permissions:\n      contents: write" not in release_job:
        errors.append("explicitly confirmed release job must retain contents: write")

    return errors


SAFE_WORKFLOW = f"""\
name: Release
on:
  workflow_dispatch:
    inputs:
      confirm_release:
        description: Type {CONFIRMATION_TOKEN} to create the release.
        required: true
        type: string
permissions: {{}}
jobs:
  release:
    permissions:
      contents: write
    steps:
      - name: Validate manual release gate
        env:
          RELEASE_CONFIRMATION: ${{{{ inputs.confirm_release }}}}
          SELECTED_REF: ${{{{ github.ref }}}}
        run: |
          if [[ "$RELEASE_CONFIRMATION" != "{CONFIRMATION_TOKEN}" ]]; then
            exit 1
          fi
          if [[ "$SELECTED_REF" != "{MAIN_REF}" ]]; then
            exit 1
          fi
      - uses: actions/checkout@v6
      - name: Read SDK version and stats
        run: true
      - name: Create or update release
        run: |
          gh release view "$TAG"
          gh release create "$TAG"
"""


def assert_rejected(label: str, workflow: str, expected_error: str) -> None:
    errors = validate(workflow)
    if expected_error not in errors:
        raise AssertionError(f"{label} must report {expected_error!r}, got {errors!r}")


def run_self_test() -> None:
    if errors := validate(SAFE_WORKFLOW):
        raise AssertionError(f"safe workflow rejected: {errors}")
    assert_rejected(
        "push trigger",
        SAFE_WORKFLOW.replace("workflow_dispatch:", "push:\n    branches: [main]\n  workflow_dispatch:", 1),
        "workflow triggers must be workflow_dispatch only; push-triggered releases are forbidden",
    )
    assert_rejected(
        "missing confirmation",
        SAFE_WORKFLOW.replace("confirm_release:", "release_now:", 1),
        "workflow_dispatch must require the confirm_release input",
    )
    assert_rejected(
        "wrong gate confirmation",
        SAFE_WORKFLOW.replace(
            'if [[ "$RELEASE_CONFIRMATION" != "CONFIRM_RELEASE" ]]',
            'if [[ "$RELEASE_CONFIRMATION" != "WRONG_TOKEN" ]]',
            1,
        ),
        f'manual gate must fail closed with \'"$RELEASE_CONFIRMATION" != "{CONFIRMATION_TOKEN}"\'',
    )
    assert_rejected(
        "undocumented confirmation",
        SAFE_WORKFLOW.replace(f"Type {CONFIRMATION_TOKEN}", "Type WRONG_TOKEN", 1),
        "confirm_release must document the fixed confirmation token",
    )
    assert_rejected(
        "non-main ref",
        SAFE_WORKFLOW.replace(MAIN_REF, "refs/heads/release", 1),
        f'manual gate must fail closed with \'"$SELECTED_REF" != "{MAIN_REF}"\'',
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run built-in mutation cases before validating the selected workflow",
    )
    args = parser.parse_args()

    if args.self_test:
        run_self_test()

    errors = validate(args.workflow.read_text())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Public release workflow gate passed: {args.workflow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
