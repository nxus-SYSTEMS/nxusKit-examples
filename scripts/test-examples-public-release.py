#!/usr/bin/env python3
"""Unit tests for the fail-closed Examples public-release planner."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


CONTROLLER = Path(__file__).with_name("examples-public-release.py")
SPEC = importlib.util.spec_from_file_location("examples_public_release", CONTROLLER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"unable to load {CONTROLLER}")
release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release
SPEC.loader.exec_module(release)


EXPECTED_SHA = "1" * 40
OTHER_SHA = "2" * 40
TAG = "v1.0.5-202607301720"
SDK_VERSION = "1.0.5"
TITLE = f"nxusKit Examples {TAG}"
NOTES = "source-only notes"
OBSERVED_AT = datetime(2026, 7, 30, 17, 20, tzinfo=timezone.utc)
EXECUTION_ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_REPOSITORY": "nxus-SYSTEMS/nxusKit-examples",
    "GITHUB_SHA": EXPECTED_SHA,
    "GH_TOKEN": "canary-secret-value",
}


def observation(
    *,
    remote_tag_commit: str | None,
    release_tag: str | None,
    expected_sha: str = EXPECTED_SHA,
) -> release.ReleaseObservation:
    return release.ReleaseObservation(
        expected_sha=expected_sha,
        sdk_version=SDK_VERSION,
        tag=TAG,
        remote_tag_commit=remote_tag_commit,
        release_tag=release_tag,
        title=TITLE,
        notes=NOTES,
    )


class PlannerTests(unittest.TestCase):
    def assert_plan(
        self,
        source: release.ReleaseObservation,
        action: release.ReleaseAction,
    ) -> None:
        plan = release.plan_release(source)
        self.assertEqual(plan.action, action)
        self.assertEqual(plan.expected_sha, source.expected_sha)
        self.assertEqual(plan.sdk_version, source.sdk_version)
        self.assertEqual(plan.tag, source.tag)
        self.assertEqual(plan.title, source.title)
        self.assertEqual(plan.notes, source.notes)

    def test_absent_tag_and_release_create_both(self) -> None:
        self.assert_plan(
            observation(remote_tag_commit=None, release_tag=None),
            release.ReleaseAction.CREATE_TAG_AND_RELEASE,
        )

    def test_matching_tag_without_release_creates_release_only(self) -> None:
        self.assert_plan(
            observation(remote_tag_commit=EXPECTED_SHA, release_tag=None),
            release.ReleaseAction.CREATE_RELEASE_FROM_EXISTING_TAG,
        )

    def test_matching_tag_and_release_are_idempotent(self) -> None:
        self.assert_plan(
            observation(remote_tag_commit=EXPECTED_SHA, release_tag=TAG),
            release.ReleaseAction.NO_OP,
        )

    def test_rejects_tag_at_a_different_commit(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release tag points to a different commit",
        ):
            release.plan_release(
                observation(remote_tag_commit=OTHER_SHA, release_tag=None)
            )

    def test_rejects_orphaned_release(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release exists without the generated tag",
        ):
            release.plan_release(observation(remote_tag_commit=None, release_tag=TAG))

    def test_rejects_mismatched_release_identity(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release identity does not match the generated tag",
        ):
            release.plan_release(
                observation(remote_tag_commit=EXPECTED_SHA, release_tag="v1.0.5-else")
            )

    def test_rejects_release_with_tag_at_another_commit(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release tag points to a different commit",
        ):
            release.plan_release(
                observation(remote_tag_commit=OTHER_SHA, release_tag=TAG)
            )

    def test_rejects_malformed_expected_sha(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "expected SHA must be a 40-character lowercase hexadecimal value",
        ):
            release.plan_release(
                observation(
                    remote_tag_commit=None, release_tag=None, expected_sha="bad"
                )
            )

    def test_rejects_malformed_remote_tag_commit(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "remote tag commit must be a 40-character lowercase hexadecimal value",
        ):
            release.plan_release(
                observation(remote_tag_commit="not-a-commit", release_tag=None)
            )

    def test_rejects_an_unknown_state(self) -> None:
        unknown = observation(remote_tag_commit=None, release_tag=None)
        object.__setattr__(unknown, "remote_tag_commit", object())
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release state is not supported",
        ):
            release.plan_release(unknown)


@dataclass
class FakeRunner:
    results: list[release.CommandResult]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: Sequence[str]) -> release.CommandResult:
        call = tuple(argv)
        self.calls.append(call)
        if not self.results:
            raise AssertionError(f"unexpected command: {call!r}")
        return self.results.pop(0)


def result(
    returncode: int = 0,
    *,
    stdout: str = "",
    stderr: str = "",
) -> release.CommandResult:
    return release.CommandResult(
        argv=(),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def github_writes(calls: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    return [call for call in calls if call[:3] == ("gh", "release", "create")]


class ObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.manifest_path = Path(self.temporary.name) / "manifest.json"
        self.manifest_path.write_text(
            json.dumps(
                {
                    "examples": [
                        {"languages": ["python", "rust"]},
                        {"languages": ["bash", "go"]},
                        {"languages": ["python", "bash"]},
                    ]
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def absent_results(self) -> list[release.CommandResult]:
        return [
            result(stdout=f"{EXPECTED_SHA}\n"),
            result(stdout="sdk-v1.0.5\n"),
            result(2),
            result(1, stdout='HTTP/2 404 Not Found\n{"message":"Not Found"}\n'),
        ]

    def observe(
        self, results: list[release.CommandResult]
    ) -> release.ReleaseObservation:
        self.runner = FakeRunner(results)
        return release.observe_release(
            self.runner,
            expected_sha=EXPECTED_SHA,
            at=OBSERVED_AT,
            manifest_path=self.manifest_path,
        )

    def assert_read_only_calls(self, calls: list[tuple[str, ...]]) -> None:
        forbidden_prefixes = (
            ("gh", "release", "create"),
            ("gh", "release", "edit"),
            ("gh", "release", "delete"),
            ("git", "tag"),
            ("git", "push"),
        )
        for call in calls:
            self.assertFalse(
                any(call[: len(prefix)] == prefix for prefix in forbidden_prefixes),
                call,
            )

    def test_observes_absent_state_with_deterministic_metadata(self) -> None:
        observed = self.observe(self.absent_results())
        self.assertEqual(observed.expected_sha, EXPECTED_SHA)
        self.assertEqual(observed.sdk_version, SDK_VERSION)
        self.assertEqual(observed.tag, TAG)
        self.assertIsNone(observed.remote_tag_commit)
        self.assertIsNone(observed.release_tag)
        self.assertEqual(observed.title, TITLE)
        self.assertEqual(
            observed.notes,
            f"""## nxusKit Examples {TAG}

3 examples (2 with Python, 2 with CLI/Bash) in Rust, Go, Python, and CLI/Bash — compatible with nxusKit SDK v{SDK_VERSION}.

### Download

Download the source archive below to get all examples with scenario data,
conformance manifests, and helper scripts.

> **Note:** Examples require the [nxusKit SDK](https://github.com/nxus-SYSTEMS/nxusKit)
> v{SDK_VERSION}+ to build and run. See the
> [README](https://github.com/nxus-SYSTEMS/nxusKit-examples#quick-start)
> for setup instructions.
""",
        )
        self.assertEqual(
            self.runner.calls,
            [
                ("git", "rev-parse", "HEAD"),
                (
                    "gh",
                    "release",
                    "view",
                    "--repo",
                    "nxus-SYSTEMS/nxusKit",
                    "--json",
                    "tagName",
                    "--jq",
                    ".tagName",
                ),
                (
                    "git",
                    "ls-remote",
                    "--exit-code",
                    "--tags",
                    "origin",
                    f"refs/tags/{TAG}",
                    f"refs/tags/{TAG}^{{}}",
                ),
                (
                    "gh",
                    "api",
                    "--include",
                    f"repos/nxus-SYSTEMS/nxusKit-examples/releases/tags/{TAG}",
                    "--jq",
                    "{tag_name: .tag_name}",
                ),
            ],
        )
        self.assert_read_only_calls(self.runner.calls)

    def test_accepts_matching_checkout_and_lightweight_tag(self) -> None:
        runner = FakeRunner(
            [
                result(stdout=f"{EXPECTED_SHA}\n"),
                result(stdout="sdk-v1.0.5\n"),
                result(stdout=f"{EXPECTED_SHA}\trefs/tags/{TAG}\n"),
                result(1, stdout='HTTP/2 404 Not Found\n{"message":"Not Found"}\n'),
            ]
        )
        observed = release.observe_release(
            runner,
            expected_sha=EXPECTED_SHA,
            at=OBSERVED_AT,
            manifest_path=self.manifest_path,
        )
        self.assertEqual(observed.remote_tag_commit, EXPECTED_SHA)
        self.assertIsNone(observed.release_tag)
        self.assert_read_only_calls(runner.calls)

    def test_prefers_peeled_annotated_tag_target(self) -> None:
        runner = FakeRunner(
            [
                result(
                    stdout=(
                        f"{OTHER_SHA}\trefs/tags/{TAG}\n"
                        f"{EXPECTED_SHA}\trefs/tags/{TAG}^{{}}\n"
                    )
                ),
                result(1, stdout='HTTP/2 404 Not Found\n{"message":"Not Found"}\n'),
            ]
        )
        remote_tag, release_tag = release.observe_remote_state(runner, tag=TAG)
        self.assertEqual(remote_tag, EXPECTED_SHA)
        self.assertIsNone(release_tag)
        self.assert_read_only_calls(runner.calls)

    def test_accepts_exact_release_response(self) -> None:
        runner = FakeRunner(
            [
                result(stdout=f"{EXPECTED_SHA}\trefs/tags/{TAG}\n"),
                result(
                    stdout=(
                        "HTTP/2 200 OK\n"
                        "content-type: application/json\n\n"
                        f'{{"tag_name":"{TAG}"}}\n'
                    )
                ),
            ]
        )
        remote_tag, release_tag = release.observe_remote_state(runner, tag=TAG)
        self.assertEqual(remote_tag, EXPECTED_SHA)
        self.assertEqual(release_tag, TAG)
        self.assertEqual(
            runner.calls[-1],
            (
                "gh",
                "api",
                "--include",
                f"repos/nxus-SYSTEMS/nxusKit-examples/releases/tags/{TAG}",
                "--jq",
                "{tag_name: .tag_name}",
            ),
        )
        self.assert_read_only_calls(runner.calls)

    def test_rejects_checkout_mismatch(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "checked-out commit does not match expected SHA",
        ):
            self.observe(
                [
                    result(stdout=f"{OTHER_SHA}\n"),
                    result(stdout="sdk-v1.0.5\n"),
                    result(2),
                    result(1, stdout='HTTP/2 404 Not Found\n{"message":"Not Found"}\n'),
                ]
            )
        self.assertEqual(self.runner.calls, [("git", "rev-parse", "HEAD")])

    def test_rejects_malformed_sdk_release_tag(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "SDK release tag must use sdk-vX.Y.Z",
        ):
            self.observe(
                [
                    result(stdout=f"{EXPECTED_SHA}\n"),
                    result(stdout="v1.0.5\n"),
                    result(2),
                    result(1, stdout="HTTP/2 404 Not Found\n"),
                ]
            )
        self.assert_read_only_calls(self.runner.calls)

    def test_rejects_malformed_remote_tag_response(self) -> None:
        runner = FakeRunner(
            [
                result(stdout=f"{EXPECTED_SHA}\trefs/tags/other\n"),
                result(1, stdout='HTTP/2 404 Not Found\n{"message":"Not Found"}\n'),
            ]
        )
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "remote tag response is malformed",
        ):
            release.observe_remote_state(runner, tag=TAG)
        self.assert_read_only_calls(runner.calls)

    def test_rejects_unknown_remote_tag_status(self) -> None:
        runner = FakeRunner([result(1, stderr="transport failed\n")])
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "unable to determine remote tag state",
        ):
            release.observe_remote_state(runner, tag=TAG)
        self.assert_read_only_calls(runner.calls)

    def test_rejects_mismatched_or_malformed_release_response(self) -> None:
        for payload, error in (
            (
                'HTTP/2 200 OK\n\n{"tag_name":"v1.0.5-other"}\n',
                "release response tag_name does not match generated tag",
            ),
            (
                f'HTTP/2 200 OK\n\n{{"tag_name":"{TAG}","id":1}}\n',
                "release response must contain only tag_name",
            ),
            ("HTTP/2 500 Internal Server Error\n", "unable to determine release state"),
        ):
            with self.subTest(payload=payload):
                runner = FakeRunner(
                    [
                        result(2),
                        result(0, stdout=payload),
                    ]
                )
                with self.assertRaisesRegex(release.ReleaseContractError, error):
                    release.observe_remote_state(runner, tag=TAG)
                self.assert_read_only_calls(runner.calls)

    def test_rejects_full_release_object_without_projection(self) -> None:
        runner = FakeRunner(
            [
                result(2),
                result(
                    stdout=(
                        "HTTP/2 200 OK\n"
                        "content-type: application/json\n\n"
                        f'{{"url":"https://api.github.example/releases/1","tag_name":"{TAG}","id":1}}\n'
                    )
                ),
            ]
        )
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release response must contain only tag_name",
        ):
            release.observe_remote_state(runner, tag=TAG)
        self.assert_read_only_calls(runner.calls)

    def test_rejects_multiple_or_contradictory_http_status_lines(self) -> None:
        for returncode, payload in (
            (
                0,
                (f'HTTP/2 200 OK\nHTTP/2 404 Not Found\n\n{{"tag_name":"{TAG}"}}\n'),
            ),
            (
                1,
                'HTTP/2 404 Not Found\nHTTP/2 404 Not Found\n{"message":"Not Found"}\n',
            ),
        ):
            with self.subTest(returncode=returncode, payload=payload):
                runner = FakeRunner([result(2), result(returncode, stdout=payload)])
                with self.assertRaisesRegex(
                    release.ReleaseContractError,
                    "release response must contain exactly one HTTP status line",
                ):
                    release.observe_remote_state(runner, tag=TAG)
                self.assert_read_only_calls(runner.calls)

    def test_rejects_malformed_manifest(self) -> None:
        self.manifest_path.write_text('{"examples":"not-a-list"}')
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "manifest examples must be a list",
        ):
            self.observe(self.absent_results())
        self.assert_read_only_calls(self.runner.calls)


class ExecutionTests(ObservationTests):
    def remote_state_results(
        self, remote_tag_commit: str | None, release_tag: str | None
    ) -> list[release.CommandResult]:
        tag_result = (
            result(2)
            if remote_tag_commit is None
            else result(stdout=f"{remote_tag_commit}\trefs/tags/{TAG}\n")
        )
        release_result = (
            result(1, stdout='HTTP/2 404 Not Found\n{"message":"Not Found"}\n')
            if release_tag is None
            else result(
                stdout=(
                    "HTTP/2 200 OK\n"
                    "content-type: application/json\n\n"
                    f'{{"tag_name":"{release_tag}"}}\n'
                )
            )
        )
        return [tag_result, release_result]

    def controller_results(
        self,
        *,
        initial_tag: str | None = None,
        initial_release: str | None = None,
        revalidated_tag: str | None = None,
        revalidated_release: str | None = None,
        write: release.CommandResult | None = None,
    ) -> list[release.CommandResult]:
        results = [
            result(stdout=f"{EXPECTED_SHA}\n"),
            result(stdout="sdk-v1.0.5\n"),
            *self.remote_state_results(initial_tag, initial_release),
        ]
        if revalidated_tag is not None or revalidated_release is not None or write:
            results.extend(
                self.remote_state_results(revalidated_tag, revalidated_release)
            )
        if write is not None:
            results.append(write)
        return results

    def run_controller(
        self,
        results: list[release.CommandResult],
        *,
        execute: bool,
        env: dict[str, str] | None = None,
        confirmation: str = "CONFIRM_RELEASE",
    ) -> release.ReleasePlan:
        self.runner = FakeRunner(results)
        return release.run_release(
            self.runner,
            EXECUTION_ENV if env is None else env,
            expected_sha=EXPECTED_SHA,
            confirmation=confirmation,
            execute=execute,
            at=OBSERVED_AT,
            manifest_path=self.manifest_path,
        )

    def assert_no_secret_or_write(self, error: Exception) -> None:
        self.assertNotIn(EXECUTION_ENV["GH_TOKEN"], str(error))
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(github_writes(self.runner.calls), [])

    def test_execution_context_failures_reject_before_observation(self) -> None:
        invalid_contexts = [
            ("confirmation", EXECUTION_ENV, "wrong-confirmation"),
            ("missing confirmation", EXECUTION_ENV, ""),
        ]
        for key, expected in (
            ("GITHUB_ACTIONS", "false"),
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_REPOSITORY", "other/repository"),
            ("GITHUB_SHA", OTHER_SHA),
        ):
            invalid_env = dict(EXECUTION_ENV)
            invalid_env[key] = expected
            invalid_contexts.append((key, invalid_env, "CONFIRM_RELEASE"))

        for name, environment, confirmation in invalid_contexts:
            with self.subTest(name=name):
                with self.assertRaises(release.ReleaseContractError) as raised:
                    self.run_controller(
                        [],
                        execute=True,
                        env=environment,
                        confirmation=confirmation,
                    )
                self.assert_no_secret_or_write(raised.exception)

    def test_malformed_expected_sha_rejects_before_observation(self) -> None:
        self.runner = FakeRunner([])
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "expected SHA must be a 40-character lowercase hexadecimal value",
        ) as raised:
            release.run_release(
                self.runner,
                EXECUTION_ENV,
                expected_sha="bad",
                confirmation="CONFIRM_RELEASE",
                execute=True,
                at=OBSERVED_AT,
                manifest_path=self.manifest_path,
            )
        self.assert_no_secret_or_write(raised.exception)

    def test_plan_only_returns_plan_and_uses_only_reads(self) -> None:
        planned = self.run_controller(self.controller_results(), execute=False)
        self.assertEqual(planned.action, release.ReleaseAction.CREATE_TAG_AND_RELEASE)
        self.assertEqual(len(self.runner.calls), 4)
        self.assert_read_only_calls(self.runner.calls)
        self.assertEqual(github_writes(self.runner.calls), [])

    def test_no_op_executes_no_write(self) -> None:
        planned = self.run_controller(
            self.controller_results(initial_tag=EXPECTED_SHA, initial_release=TAG),
            execute=True,
        )
        self.assertEqual(planned.action, release.ReleaseAction.NO_OP)
        self.assertEqual(len(self.runner.calls), 4)
        self.assertEqual(github_writes(self.runner.calls), [])

    def test_absent_state_executes_one_exact_create_command_after_revalidation(
        self,
    ) -> None:
        planned = self.run_controller(
            self.controller_results(
                write=result(stdout="created\n"),
            ),
            execute=True,
        )
        self.assertEqual(planned.action, release.ReleaseAction.CREATE_TAG_AND_RELEASE)
        writes = github_writes(self.runner.calls)
        self.assertEqual(
            writes,
            [
                (
                    "gh",
                    "release",
                    "create",
                    TAG,
                    "--target",
                    EXPECTED_SHA,
                    "--title",
                    TITLE,
                    "--notes",
                    planned.notes,
                    "--latest",
                )
            ],
        )
        self.assertNotIn("--verify-tag", writes[0])
        self.assertEqual(len(self.runner.calls), 7)

    def test_existing_tag_executes_one_exact_verified_release_command(self) -> None:
        planned = self.run_controller(
            self.controller_results(
                initial_tag=EXPECTED_SHA,
                revalidated_tag=EXPECTED_SHA,
                write=result(stdout="created\n"),
            ),
            execute=True,
        )
        self.assertEqual(
            github_writes(self.runner.calls),
            [
                (
                    "gh",
                    "release",
                    "create",
                    TAG,
                    "--verify-tag",
                    "--title",
                    TITLE,
                    "--notes",
                    planned.notes,
                    "--latest",
                )
            ],
        )
        self.assertNotIn("--target", github_writes(self.runner.calls)[0])

    def test_revalidation_drift_rejects_before_write(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release state changed before execution",
        ):
            self.run_controller(
                self.controller_results(revalidated_tag=EXPECTED_SHA), execute=True
            )
        self.assertEqual(len(self.runner.calls), 6)
        self.assertEqual(github_writes(self.runner.calls), [])

    def test_revalidation_read_failure_rejects_before_write(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "unable to determine remote tag state",
        ):
            self.run_controller(
                [
                    *self.controller_results(),
                    result(1, stderr="read failed\n"),
                ],
                execute=True,
            )
        self.assertEqual(github_writes(self.runner.calls), [])

    def test_failed_write_raises_without_success_output(self) -> None:
        with self.assertRaisesRegex(
            release.ReleaseContractError,
            "release creation command failed",
        ):
            self.run_controller(
                self.controller_results(
                    write=result(1, stdout="failure payload\n", stderr="bad write\n")
                ),
                execute=True,
            )
        self.assertEqual(len(github_writes(self.runner.calls)), 1)

    def test_runner_never_receives_shell_or_unbound_identity(self) -> None:
        self.run_controller(
            self.controller_results(write=result(stdout="created\n")), execute=True
        )
        for call in self.runner.calls:
            self.assertIsInstance(call, tuple)
            self.assertNotIn("$OTHER_TAG", call)
            self.assertNotIn(OTHER_SHA, call)

    def test_cli_defaults_to_plan_only_and_bounds_output(self) -> None:
        runner = FakeRunner(self.controller_results())
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = release.main(
                ["--expected-sha", EXPECTED_SHA],
                runner=runner,
                env=EXECUTION_ENV,
                at=OBSERVED_AT,
                manifest_path=self.manifest_path,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "action": "create_tag_and_release",
                "expected_sha": EXPECTED_SHA,
                "sdk_version": SDK_VERSION,
                "tag": TAG,
            },
        )
        self.assertNotIn(EXECUTION_ENV["GH_TOKEN"], output.getvalue())
        self.assert_read_only_calls(runner.calls)
        self.assertEqual(github_writes(runner.calls), [])

    def test_cli_execution_rejection_does_not_emit_a_secret(self) -> None:
        runner = FakeRunner([])
        error = io.StringIO()
        with redirect_stderr(error):
            exit_code = release.main(
                [
                    "--expected-sha",
                    EXPECTED_SHA,
                    "--confirmation",
                    "incorrect",
                    "--execute",
                ],
                runner=runner,
                env=EXECUTION_ENV,
                at=OBSERVED_AT,
                manifest_path=self.manifest_path,
            )
        self.assertEqual(exit_code, 1)
        self.assertNotIn(EXECUTION_ENV["GH_TOKEN"], error.getvalue())
        self.assertEqual(runner.calls, [])


if __name__ == "__main__":
    unittest.main()
