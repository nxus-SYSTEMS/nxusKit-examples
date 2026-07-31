#!/usr/bin/env python3
"""Validate the fixed Examples public Release workflow snapshot and layout."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path


PRIVATE_WORKFLOW = Path(".github/workflows-public/release.yml")
PUBLIC_WORKFLOW = Path(".github/workflows/release.yml")
SNAPSHOT = Path("conformance/public_release_workflow.snapshot.yml")
CONTROLLER = "scripts/examples-public-release.py"
FORBIDDEN_WORKFLOW_AUTHORITIES = (
    "gh release create",
    "gh release edit",
    "gh release delete",
    "git tag ",
)
PRIVATE_PUBLICATION_WORKFLOWS = {
    "publish-to-public.yml",
    "publish-to-public.yaml",
    "publish-to-docs.yml",
    "publish-to-docs.yaml",
}
TAG_REF_PUSH = re.compile(r"git\s+push\b[^\n]*refs/tags/", flags=re.IGNORECASE)
GITHUB_API_WRITE = re.compile(
    r"gh\s+api\b[^\n]*(?:--method\s+|-X\s+)(?:POST|PUT|PATCH|DELETE)\b",
    flags=re.IGNORECASE,
)


def workflow_paths(root: Path) -> list[Path]:
    """Return every workflow source in either private or exported layout."""

    paths: set[Path] = set()
    for directory in (root / ".github/workflows", root / ".github/workflows-public"):
        if directory.is_dir():
            paths.update(directory.rglob("*.yml"))
            paths.update(directory.rglob("*.yaml"))
    return sorted(paths)


def expected_workflow(layout: str) -> tuple[Path, Path]:
    """Resolve one explicit layout without silently selecting an alternative."""

    if layout == "private":
        return PRIVATE_WORKFLOW, PUBLIC_WORKFLOW
    if layout == "public":
        return PUBLIC_WORKFLOW, PRIVATE_WORKFLOW
    raise ValueError("layout must be private or public")


def validate_repository(root: Path, layout: str) -> list[str]:
    """Return stable snapshot/layout violations without parsing shell syntax."""

    errors: list[str] = []
    try:
        expected, opposite = expected_workflow(layout)
    except ValueError as exc:
        return [str(exc)]

    workflow = root / expected
    snapshot = root / SNAPSHOT
    opposite_workflow = root / opposite
    if not workflow.is_file():
        errors.append(f"required release workflow is missing: {expected}")
    if not snapshot.is_file():
        errors.append(f"release workflow snapshot is missing: {SNAPSHOT}")
    if workflow.is_file() and snapshot.is_file():
        try:
            if workflow.read_bytes() != snapshot.read_bytes():
                errors.append("release workflow must match snapshot exactly")
        except OSError:
            errors.append("release workflow or snapshot could not be read")
    if opposite_workflow.is_file():
        errors.append(f"opposite release workflow must be absent: {opposite}")

    controller_occurrences: list[Path] = []
    for path in workflow_paths(root):
        try:
            content = path.read_text()
        except OSError:
            errors.append(f"workflow could not be read: {path.relative_to(root)}")
            continue
        relative = path.relative_to(root)
        controller_occurrences.extend([relative] * content.count(CONTROLLER))
        for authority in FORBIDDEN_WORKFLOW_AUTHORITIES:
            if authority in content:
                errors.append(
                    f"forbidden workflow authority in {relative}: {authority}"
                )
        if (
            "gh api" in content
            and "/releases/" in content
            and GITHUB_API_WRITE.search(content) is not None
        ):
            errors.append(f"forbidden Release API write in {relative}")
        if TAG_REF_PUSH.search(content) is not None:
            errors.append(f"forbidden tag-ref push in {relative}")
        if layout == "public" and path.name in PRIVATE_PUBLICATION_WORKFLOWS:
            errors.append(
                f"private publication workflow is forbidden in public layout: {relative}"
            )

    expected_relative = expected
    if len(controller_occurrences) != 1:
        errors.append("workflows must contain the release controller exactly once")
    elif controller_occurrences[0] != expected_relative:
        errors.append(
            "release controller must appear only in the expected release workflow"
        )
    return errors


CANONICAL_WORKFLOW = """\
# CD — Create a manually confirmed, source-only public Examples Release.
# New tags are v<SDK-semver>-<UTC YYYYMMDDHHMM>.

name: Release

on:
  workflow_dispatch:
    inputs:
      confirm_release:
        description: Type CONFIRM_RELEASE to create a public Examples Release from main.
        required: true
        type: string

jobs:
  release:
    name: Tag and release
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Execute confirmed Examples release
        env:
          GH_TOKEN: ${{ github.token }}
          RELEASE_CONFIRMATION: ${{ inputs.confirm_release }}
        run: >-
          python3 scripts/examples-public-release.py
          --expected-sha "$GITHUB_SHA"
          --confirmation "$RELEASE_CONFIRMATION"
          --execute
"""


def write_layout(root: Path, layout: str, workflow: str = CANONICAL_WORKFLOW) -> Path:
    """Create one disposable private or exported-public workflow layout."""

    expected, _ = expected_workflow(layout)
    workflow_path = root / expected
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(workflow)
    snapshot = root / SNAPSHOT
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(CANONICAL_WORKFLOW)
    return workflow_path


def assert_layout_rejected(root: Path, layout: str, label: str) -> None:
    """Require a one-property mutation to fail closed."""

    if not validate_repository(root, layout):
        raise AssertionError(f"{label} must be rejected")


def run_self_test() -> None:
    """Exercise snapshot/layout rejection without dispatching a workflow."""

    source_mutations = {
        "inline create": lambda text: (
            text + "\n      - run: gh release create unsafe\n"
        ),
        "inline edit": lambda text: text + "\n      - run: gh release edit unsafe\n",
        "GitHub API write": lambda text: (
            text + "\n      - run: gh api --method POST repos/example/releases\n"
        ),
        "git tag": lambda text: text + "\n      - run: git tag unsafe\n",
        "tag-ref push": lambda text: (
            text + "\n      - run: git push origin refs/tags/unsafe\n"
        ),
        "duplicate controller": lambda text: (
            text + "\n      - run: python3 scripts/examples-public-release.py\n"
        ),
        "extra run step": lambda text: text + "\n      - run: echo extra\n",
        "changed trigger": lambda text: text.replace("workflow_dispatch:", "push:", 1),
        "changed confirmation": lambda text: text.replace(
            "CONFIRM_RELEASE", "WRONG_CONFIRMATION", 1
        ),
        "changed expected SHA": lambda text: text.replace(
            '--expected-sha "$GITHUB_SHA"', '--expected-sha "$OTHER_SHA"', 1
        ),
        "changed confirmation argument": lambda text: text.replace(
            '--confirmation "$RELEASE_CONFIRMATION"', "--confirmation wrong", 1
        ),
        "missing execute argument": lambda text: text.replace("--execute", "", 1),
        "broadened permissions": lambda text: text.replace(
            "contents: write", "contents: write\n      actions: write", 1
        ),
        "other tag target bypass": lambda text: text.replace(
            '"$GITHUB_SHA"', '"$OTHER_TAG"', 1
        ),
        "swapped write bypass": lambda text: (
            text
            + "\n      - run: gh release create unsafe --verify-tag --target $OTHER_TAG\n"
        ),
        "later release write bypass": lambda text: (
            text
            + "\n      - name: Later write\n        run: gh release create unsafe\n"
        ),
        "compound release write bypass": lambda text: (
            text + "\n      - run: true && gh release create unsafe\n"
        ),
    }
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = write_layout(root, "private")
        if errors := validate_repository(root, "private"):
            raise AssertionError(f"private canonical workflow rejected: {errors}")
        for label, mutate in source_mutations.items():
            source.write_text(mutate(CANONICAL_WORKFLOW))
            assert_layout_rejected(root, "private", label)
            source.write_text(CANONICAL_WORKFLOW)
        public_release = root / PUBLIC_WORKFLOW
        public_release.parent.mkdir(parents=True, exist_ok=True)
        public_release.write_text(CANONICAL_WORKFLOW)
        assert_layout_rejected(root, "private", "private workflow restoration")
        public_release.unlink()
        snapshot = root / SNAPSHOT
        snapshot.write_text("snapshot drift\n")
        assert_layout_rejected(root, "private", "private snapshot drift")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        write_layout(root, "public")
        if errors := validate_repository(root, "public"):
            raise AssertionError(f"public canonical workflow rejected: {errors}")
        read_only_tag = root / ".github/workflows/tag-inspection.yml"
        read_only_tag.parent.mkdir(parents=True, exist_ok=True)
        read_only_tag.write_text("run: git ls-remote origin refs/tags/read-only\n")
        if errors := validate_repository(root, "public"):
            raise AssertionError(f"read-only tag inspection rejected: {errors}")
        snapshot = root / SNAPSHOT
        snapshot.write_text("snapshot drift\n")
        assert_layout_rejected(root, "public", "public snapshot drift")
        snapshot.write_text(CANONICAL_WORKFLOW)
        private_release = root / PRIVATE_WORKFLOW
        private_release.parent.mkdir(parents=True, exist_ok=True)
        private_release.write_text(CANONICAL_WORKFLOW)
        assert_layout_rejected(root, "public", "public private release leakage")
        private_release.unlink()
        mirror = root / ".github/workflows/publish-to-public.yml"
        mirror.write_text("name: private mirror\n")
        assert_layout_rejected(root, "public", "public mirror workflow leakage")
        mirror.unlink()
        docs = root / ".github/workflows/publish-to-docs.yml"
        docs.write_text("name: private docs\n")
        assert_layout_rejected(root, "public", "public Docs workflow leakage")


def main() -> int:
    """Run self-tests, then validate one private or exported-public layout."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--layout", choices=("private", "public"), default="private")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
    errors = validate_repository(args.repository_root, args.layout)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "Public release workflow snapshot/layout gate passed: "
        f"{args.repository_root / expected_workflow(args.layout)[0]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
