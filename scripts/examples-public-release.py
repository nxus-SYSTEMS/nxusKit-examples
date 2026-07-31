#!/usr/bin/env python3
"""Plan the one permitted public Examples Release without side effects."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping, Protocol


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
HTTP_STATUS_PATTERN = re.compile(
    r"^HTTP/[^\s]+ (?P<code>[0-9]{3})(?:\s|$)", flags=re.MULTILINE
)
SDK_REPOSITORY = "nxus-SYSTEMS/nxusKit"
EXAMPLES_REPOSITORY = "nxus-SYSTEMS/nxusKit-examples"
RELEASE_CONFIRMATION = "CONFIRM_RELEASE"
REQUIRED_EXECUTION_ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_REPOSITORY": EXAMPLES_REPOSITORY,
}


class ReleaseContractError(RuntimeError):
    """A stable fail-closed public-release contract error."""


class ReleaseAction(Enum):
    """The only outcomes permitted by the public-release contract."""

    NO_OP = "no_op"
    CREATE_RELEASE_FROM_EXISTING_TAG = "create_release_from_existing_tag"
    CREATE_TAG_AND_RELEASE = "create_tag_and_release"


@dataclass(frozen=True)
class ReleaseObservation:
    """Immutable remote release state already bound to a generated tag."""

    expected_sha: str
    sdk_version: str
    tag: str
    remote_tag_commit: str | None
    release_tag: str | None
    title: str
    notes: str


@dataclass(frozen=True)
class ReleasePlan:
    """An immutable, side-effect-free decision derived from an observation."""

    action: ReleaseAction
    expected_sha: str
    sdk_version: str
    tag: str
    title: str
    notes: str
    reason: str


@dataclass(frozen=True)
class CommandResult:
    """The complete result of one structured external command."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """A structured command boundary suitable for a recording fake in tests."""

    def run(self, argv: Sequence[str]) -> CommandResult:
        """Run exactly one argument vector without shell interpretation."""


class SubprocessRunner:
    """The production structured command runner."""

    def run(self, argv: Sequence[str]) -> CommandResult:
        command = tuple(argv)
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
        return CommandResult(
            argv=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def validate_commit_sha(value: str, *, subject: str) -> None:
    """Reject any commit identity that is not a full lowercase Git SHA."""

    if not isinstance(value, str) or SHA_PATTERN.fullmatch(value) is None:
        raise ReleaseContractError(
            f"{subject} must be a 40-character lowercase hexadecimal value"
        )


def _plan(
    observation: ReleaseObservation, action: ReleaseAction, reason: str
) -> ReleasePlan:
    return ReleasePlan(
        action=action,
        expected_sha=observation.expected_sha,
        sdk_version=observation.sdk_version,
        tag=observation.tag,
        title=observation.title,
        notes=observation.notes,
        reason=reason,
    )


def plan_release(observation: ReleaseObservation) -> ReleasePlan:
    """Purely classify the exact generated-tag and Release state.

    This function deliberately performs no environment, filesystem, subprocess,
    Git, network, or GitHub operation. Unknown values and every inconsistent
    state reject rather than selecting a fallback mutation.
    """

    validate_commit_sha(observation.expected_sha, subject="expected SHA")
    remote_tag_commit = observation.remote_tag_commit
    release_tag = observation.release_tag

    if remote_tag_commit is not None and not isinstance(remote_tag_commit, str):
        raise ReleaseContractError("release state is not supported")
    if release_tag is not None and not isinstance(release_tag, str):
        raise ReleaseContractError("release state is not supported")
    if remote_tag_commit is not None:
        validate_commit_sha(remote_tag_commit, subject="remote tag commit")
        if remote_tag_commit != observation.expected_sha:
            raise ReleaseContractError("release tag points to a different commit")

    if release_tag is not None and remote_tag_commit is None:
        raise ReleaseContractError("release exists without the generated tag")
    if release_tag is not None and release_tag != observation.tag:
        raise ReleaseContractError("release identity does not match the generated tag")

    if remote_tag_commit is None and release_tag is None:
        return _plan(
            observation,
            ReleaseAction.CREATE_TAG_AND_RELEASE,
            "the generated tag and Release are absent",
        )
    if remote_tag_commit == observation.expected_sha and release_tag is None:
        return _plan(
            observation,
            ReleaseAction.CREATE_RELEASE_FROM_EXISTING_TAG,
            "the generated tag exists at the expected commit without a Release",
        )
    if remote_tag_commit == observation.expected_sha and release_tag == observation.tag:
        return _plan(
            observation,
            ReleaseAction.NO_OP,
            "the generated tag and Release already match the expected commit",
        )
    raise ReleaseContractError("release state is not supported")


def _exact_success_line(result: CommandResult, error: str) -> str:
    """Return exactly one successful output line or reject ambiguity."""

    lines = result.stdout.splitlines()
    if result.returncode != 0 or result.stderr or len(lines) != 1 or not lines[0]:
        raise ReleaseContractError(error)
    return lines[0]


def _tag_authority() -> object:
    """Load the one approved UTC-minute tag implementation by file path."""

    source = Path(__file__).with_name("examples-release-tag.py")
    spec = importlib.util.spec_from_file_location("examples_release_tag", source)
    if spec is None or spec.loader is None:
        raise ReleaseContractError("unable to load Examples release-tag authority")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _release_tag(sdk_version: str, at: datetime) -> str:
    """Delegate current UTC-minute generation and validation to tag authority."""

    authority = _tag_authority()
    try:
        tag = authority.generate_tag(sdk_version, at)
        info = authority.validate_tag(tag)
    except (AttributeError, ValueError) as exc:
        raise ReleaseContractError("SDK release tag must use sdk-vX.Y.Z") from exc
    if info.historical or info.sdk_version != sdk_version:
        raise ReleaseContractError("SDK release tag must use sdk-vX.Y.Z")
    return tag


def _sdk_version(runner: CommandRunner) -> str:
    result = runner.run(
        (
            "gh",
            "release",
            "view",
            "--repo",
            SDK_REPOSITORY,
            "--json",
            "tagName",
            "--jq",
            ".tagName",
        )
    )
    sdk_tag = _exact_success_line(result, "SDK release tag must use sdk-vX.Y.Z")
    if not sdk_tag.startswith("sdk-v"):
        raise ReleaseContractError("SDK release tag must use sdk-vX.Y.Z")
    sdk_version = sdk_tag.removeprefix("sdk-v")
    authority = _tag_authority()
    try:
        authority.validate_sdk_version(sdk_version)
    except (AttributeError, ValueError) as exc:
        raise ReleaseContractError("SDK release tag must use sdk-vX.Y.Z") from exc
    return sdk_version


def _parse_tag_lines(result: CommandResult, tag: str) -> str | None:
    """Parse only exact lightweight or annotated tag-reference responses."""

    if result.returncode == 2:
        if result.stdout or result.stderr:
            raise ReleaseContractError("unable to determine remote tag state")
        return None
    if result.returncode != 0 or result.stderr:
        raise ReleaseContractError("unable to determine remote tag state")

    entries: dict[str, str] = {}
    expected_refs = {f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or fields[1] not in expected_refs or fields[1] in entries:
            raise ReleaseContractError("remote tag response is malformed")
        entries[fields[1]] = fields[0]

    lightweight = f"refs/tags/{tag}"
    peeled = f"refs/tags/{tag}^{{}}"
    if set(entries) == {lightweight}:
        commit = entries[lightweight]
    elif set(entries) == {lightweight, peeled}:
        commit = entries[peeled]
    else:
        raise ReleaseContractError("remote tag response is malformed")
    try:
        validate_commit_sha(commit, subject="remote tag commit")
    except ReleaseContractError as exc:
        raise ReleaseContractError("remote tag response is malformed") from exc
    return commit


def _release_tag_from_response(result: CommandResult, tag: str) -> str | None:
    """Classify only an exact Release response or an anchored 404 absence."""

    combined = f"{result.stdout}{result.stderr}"
    status_lines = list(HTTP_STATUS_PATTERN.finditer(combined))
    if len(status_lines) != 1:
        raise ReleaseContractError(
            "release response must contain exactly one HTTP status line"
        )
    status_code = status_lines[0].group("code")
    if result.returncode == 1:
        if status_code == "404":
            return None
        raise ReleaseContractError("unable to determine release state")
    if result.returncode != 0 or result.stderr:
        raise ReleaseContractError("unable to determine release state")

    parts = result.stdout.split("\n\n")
    if len(parts) != 2 or status_code != "200":
        raise ReleaseContractError("unable to determine release state")
    try:
        payload = json.loads(parts[1])
    except json.JSONDecodeError as exc:
        raise ReleaseContractError("release response is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {"tag_name"}:
        raise ReleaseContractError("release response must contain only tag_name")
    release_tag = payload["tag_name"]
    if not isinstance(release_tag, str):
        raise ReleaseContractError("release response tag_name is malformed")
    if release_tag != tag:
        raise ReleaseContractError(
            "release response tag_name does not match generated tag"
        )
    return release_tag


def observe_remote_state(
    runner: CommandRunner, *, tag: str
) -> tuple[str | None, str | None]:
    """Observe the remote tag and Release state using read-only commands only."""

    tag_result = runner.run(
        (
            "git",
            "ls-remote",
            "--exit-code",
            "--tags",
            "origin",
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        )
    )
    remote_tag_commit = _parse_tag_lines(tag_result, tag)
    release_result = runner.run(
        (
            "gh",
            "api",
            "--include",
            f"repos/{EXAMPLES_REPOSITORY}/releases/tags/{tag}",
            "--jq",
            "{tag_name: .tag_name}",
        )
    )
    return remote_tag_commit, _release_tag_from_response(release_result, tag)


def _manifest_statistics(manifest_path: Path) -> str:
    """Derive stable public-language counts from a strict manifest shape."""

    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseContractError("manifest could not be read") from exc
    examples = manifest.get("examples") if isinstance(manifest, dict) else None
    if not isinstance(examples, list):
        raise ReleaseContractError("manifest examples must be a list")

    python_examples = 0
    bash_examples = 0
    for example in examples:
        languages = example.get("languages") if isinstance(example, dict) else None
        if not isinstance(languages, list) or not all(
            isinstance(language, str) for language in languages
        ):
            raise ReleaseContractError("manifest example languages must be a list")
        python_examples += "python" in languages
        bash_examples += "bash" in languages
    return (
        f"{len(examples)} examples ({python_examples} with Python, "
        f"{bash_examples} with CLI/Bash)"
    )


def _release_notes(tag: str, sdk_version: str, statistics: str) -> str:
    """Build deterministic source-only notes outside the workflow shell."""

    return f"""## nxusKit Examples {tag}

{statistics} in Rust, Go, Python, and CLI/Bash — compatible with nxusKit SDK v{sdk_version}.

### Download

Download the source archive below to get all examples with scenario data,
conformance manifests, and helper scripts.

> **Note:** Examples require the [nxusKit SDK](https://github.com/nxus-SYSTEMS/nxusKit)
> v{sdk_version}+ to build and run. See the
> [README](https://github.com/nxus-SYSTEMS/nxusKit-examples#quick-start)
> for setup instructions.
"""


def observe_release(
    runner: CommandRunner,
    *,
    expected_sha: str,
    at: datetime,
    manifest_path: Path,
) -> ReleaseObservation:
    """Observe complete release state without issuing a GitHub or Git write."""

    validate_commit_sha(expected_sha, subject="expected SHA")
    checkout = _exact_success_line(
        runner.run(("git", "rev-parse", "HEAD")),
        "checked-out commit does not match expected SHA",
    )
    if checkout != expected_sha:
        raise ReleaseContractError("checked-out commit does not match expected SHA")
    sdk_version = _sdk_version(runner)
    tag = _release_tag(sdk_version, at)
    remote_tag_commit, release_tag = observe_remote_state(runner, tag=tag)
    statistics = _manifest_statistics(manifest_path)
    return ReleaseObservation(
        expected_sha=expected_sha,
        sdk_version=sdk_version,
        tag=tag,
        remote_tag_commit=remote_tag_commit,
        release_tag=release_tag,
        title=f"nxusKit Examples {tag}",
        notes=_release_notes(tag, sdk_version, statistics),
    )


def validate_execution_context(
    env: Mapping[str, str], *, expected_sha: str, confirmation: str
) -> None:
    """Validate the fixed manual-workflow boundary before any external call."""

    validate_commit_sha(expected_sha, subject="expected SHA")
    if confirmation != RELEASE_CONFIRMATION:
        raise ReleaseContractError("release confirmation is invalid")
    for key, expected_value in REQUIRED_EXECUTION_ENV.items():
        if env.get(key) != expected_value:
            raise ReleaseContractError(f"execution environment must satisfy {key}")
    if env.get("GITHUB_SHA") != expected_sha:
        raise ReleaseContractError(
            "execution environment GITHUB_SHA does not match expected SHA"
        )


def execute_plan(runner: CommandRunner, plan: ReleasePlan) -> None:
    """Run the sole permitted write for an already confirmed, stable plan."""

    validate_commit_sha(plan.expected_sha, subject="expected SHA")
    if plan.action is ReleaseAction.NO_OP:
        return
    if plan.action is ReleaseAction.CREATE_RELEASE_FROM_EXISTING_TAG:
        argv = (
            "gh",
            "release",
            "create",
            plan.tag,
            "--verify-tag",
            "--title",
            plan.title,
            "--notes",
            plan.notes,
            "--latest",
        )
    elif plan.action is ReleaseAction.CREATE_TAG_AND_RELEASE:
        argv = (
            "gh",
            "release",
            "create",
            plan.tag,
            "--target",
            plan.expected_sha,
            "--title",
            plan.title,
            "--notes",
            plan.notes,
            "--latest",
        )
    else:
        raise ReleaseContractError("release action is not supported")

    result = runner.run(argv)
    if result.returncode != 0:
        raise ReleaseContractError("release creation command failed")


def run_release(
    runner: CommandRunner,
    env: Mapping[str, str],
    *,
    expected_sha: str,
    confirmation: str,
    execute: bool,
    at: datetime,
    manifest_path: Path,
) -> ReleasePlan:
    """Plan by default; execute one revalidated creation only when confirmed."""

    if execute:
        validate_execution_context(
            env, expected_sha=expected_sha, confirmation=confirmation
        )
    initial = observe_release(
        runner,
        expected_sha=expected_sha,
        at=at,
        manifest_path=manifest_path,
    )
    plan = plan_release(initial)
    if not execute or plan.action is ReleaseAction.NO_OP:
        return plan

    remote_tag_commit, release_tag = observe_remote_state(runner, tag=initial.tag)
    revalidated = replace(
        initial,
        remote_tag_commit=remote_tag_commit,
        release_tag=release_tag,
    )
    revalidated_plan = plan_release(revalidated)
    if revalidated != initial or revalidated_plan != plan:
        raise ReleaseContractError("release state changed before execution")
    execute_plan(runner, plan)
    return plan


def _argument_parser() -> argparse.ArgumentParser:
    """Construct the plan-only-by-default public release controller CLI."""

    parser = argparse.ArgumentParser(
        description="Plan or execute one confirmed Examples public Release."
    )
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
    at: datetime | None = None,
    manifest_path: Path | None = None,
) -> int:
    """Run the controller while keeping its default path incapable of writing."""

    args = _argument_parser().parse_args(argv)
    try:
        plan = run_release(
            SubprocessRunner() if runner is None else runner,
            os.environ if env is None else env,
            expected_sha=args.expected_sha,
            confirmation=args.confirmation,
            execute=args.execute,
            at=datetime.now().astimezone() if at is None else at,
            manifest_path=(
                Path("conformance/examples_manifest.json")
                if manifest_path is None
                else manifest_path
            ),
        )
    except ReleaseContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "action": plan.action.value,
                "expected_sha": plan.expected_sha,
                "sdk_version": plan.sdk_version,
                "tag": plan.tag,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
