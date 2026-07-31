#!/usr/bin/env python3
"""Deterministic contract tests for Examples UTC-minute release tags."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import unittest


UTILITY = Path(__file__).with_name("examples-release-tag.py")
SPEC = importlib.util.spec_from_file_location("examples_release_tag", UTILITY)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"unable to load {UTILITY}")
release_tag = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_tag
SPEC.loader.exec_module(release_tag)


class ReleaseTagTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(UTILITY), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_generates_utc_minute_tag(self) -> None:
        at = datetime(2026, 7, 30, 17, 20, 59, tzinfo=timezone.utc)
        self.assertEqual(
            release_tag.generate_tag("1.0.5", at),
            "v1.0.5-202607301720",
        )

    def test_converts_aware_datetime_to_utc(self) -> None:
        at = datetime(
            2026,
            7,
            30,
            19,
            20,
            tzinfo=timezone(timedelta(hours=2)),
        )
        self.assertEqual(
            release_tag.generate_tag("1.0.5", at),
            "v1.0.5-202607301720",
        )

    def test_rejects_naive_datetime_and_non_public_sdk_versions(self) -> None:
        with self.assertRaises(ValueError):
            release_tag.generate_tag("1.0.5", datetime(2026, 7, 30, 17, 20))
        for version in ("1.0", "1.0.5-rc1", "sdk-v1.0.5"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_tag.generate_tag(version, datetime.now(timezone.utc))

    def test_current_tag_validation_returns_utc_current_info(self) -> None:
        info = release_tag.validate_tag("v1.0.5-202607301720")
        self.assertEqual(info.sdk_version, "1.0.5")
        self.assertEqual(
            info.timestamp,
            datetime(2026, 7, 30, 17, 20, tzinfo=timezone.utc),
        )
        self.assertFalse(info.historical)

    def test_historical_tag_requires_explicit_compatibility(self) -> None:
        with self.assertRaises(ValueError):
            release_tag.validate_tag("v1.0.5-20260730")
        info = release_tag.validate_tag(
            "v1.0.5-20260730",
            allow_historical=True,
        )
        self.assertTrue(info.historical)
        self.assertEqual(
            info.timestamp,
            datetime(2026, 7, 30, tzinfo=timezone.utc),
        )

    def test_rejects_malformed_and_impossible_tags(self) -> None:
        rejected = (
            "examples-v1.0.5-202607301720",
            "v1.0.5-20260730172000",
            "v1.0.5-2026-07-30-1720",
            "v1.0.5-202613301720",
            "v1.0.5-202607301760",
            "v1.0.5-202602300000",
            "v1.0.5-202607301720-extra",
            "v1.0.5-2026073x1720",
        )
        for tag in rejected:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release_tag.validate_tag(tag, allow_historical=True)

    def test_impossible_timestamp_errors_are_stable(self) -> None:
        cases = (
            (
                "v1.0.5-202607301760",
                False,
                "current release tag contains an impossible UTC minute",
            ),
            (
                "v1.0.5-20260230",
                True,
                "historical release tag contains an impossible UTC date",
            ),
        )
        for tag, allow_historical, expected in cases:
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(ValueError, f"^{re.escape(expected)}$"):
                    release_tag.validate_tag(tag, allow_historical=allow_historical)
                arguments = ["validate", "--tag", tag]
                if allow_historical:
                    arguments.append("--allow-historical")
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, f"error: {expected}\n")

    def test_cli_generation_is_exact_and_historical_validation_is_explicit(self) -> None:
        generated = self.run_cli(
            "generate",
            "--sdk-version",
            "1.0.5",
            "--at",
            "2026-07-30T17:20:00Z",
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual(generated.stdout, "v1.0.5-202607301720\n")
        self.assertEqual(generated.stderr, "")

        historical = self.run_cli(
            "validate",
            "--tag",
            "v1.0.5-20260730",
            "--allow-historical",
        )
        self.assertEqual(historical.returncode, 0, historical.stderr)
        self.assertEqual(historical.stdout, "v1.0.5-20260730\n")

    def test_cli_failures_are_nonzero_and_never_emit_success_output(self) -> None:
        rejected = (
            ("validate", "--tag", "v1.0.5-20260730"),
            ("generate", "--sdk-version", "1.0.5", "--allow-historical"),
        )
        for args in rejected:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("error", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
