#!/usr/bin/env python3
"""Reject public example tests that depend on excluded repository paths."""

from __future__ import annotations

import os
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(
    os.environ.get("PUBLIC_EXAMPLE_ROOT", Path(__file__).resolve().parents[1])
).resolve()
EXAMPLES_ROOT = REPO_ROOT / "examples"
MODEL_RESEARCH_ROOT = EXAMPLES_ROOT / "integrations" / "model-research-harness"
TEST_SOURCE_SUFFIXES = {".go", ".js", ".mjs", ".py", ".rs", ".sh", ".ts"}
FORBIDDEN_PUBLIC_DEPENDENCY = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"(?:specs|private|internal)/"
    r"|(?P<quote>['\"])(?:specs|private|internal)(?P=quote)"
    r")"
)


def public_example_test_sources(root: Path = MODEL_RESEARCH_ROOT) -> list[Path]:
    """Return public Model Research sources whose names identify them as tests."""

    sources = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        is_test = (
            name == "test"
            or name.startswith("test_")
            or name.endswith("_test.go")
            or ".test." in name
        )
        if is_test and (path.suffix in TEST_SOURCE_SUFFIXES or name == "test"):
            sources.append(path)
    return sorted(sources)


def forbidden_dependencies(path: Path) -> list[str]:
    """Return excluded top-level path dependencies found in one test source."""

    violations = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        for match in FORBIDDEN_PUBLIC_DEPENDENCY.finditer(line):
            violations.append(
                f"{path.relative_to(REPO_ROOT)}:{line_number}:{match.group(0)}"
            )
    return violations


class PublicExampleReferenceTests(unittest.TestCase):
    def test_forbidden_dependency_pattern_is_path_specific(self) -> None:
        for value in (
            "specs/013/contract.json",
            "private/data.json",
            "internal/api",
            'Path("specs") / "013"',
            "root.joinpath('private', 'data.json')",
        ):
            with self.subTest(value=value):
                self.assertIsNotNone(FORBIDDEN_PUBLIC_DEPENDENCY.search(value))
        for value in ("private inference", "handled internally", "test specifications"):
            with self.subTest(value=value):
                self.assertIsNone(FORBIDDEN_PUBLIC_DEPENDENCY.search(value))

    def test_public_example_tests_do_not_depend_on_excluded_paths(self) -> None:
        violations = [
            violation
            for path in public_example_test_sources()
            for violation in forbidden_dependencies(path)
        ]
        self.assertEqual(
            violations,
            [],
            "public example tests depend on paths excluded from the public export",
        )


if __name__ == "__main__":
    unittest.main()
