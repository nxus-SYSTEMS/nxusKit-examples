#!/usr/bin/env python3
"""Generate and validate canonical nxusKit Examples release tags."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import sys


SDK_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
CURRENT_TAG_PATTERN = re.compile(
    r"^v(?P<sdk>[0-9]+\.[0-9]+\.[0-9]+)-(?P<stamp>[0-9]{12})$"
)
HISTORICAL_TAG_PATTERN = re.compile(
    r"^v(?P<sdk>[0-9]+\.[0-9]+\.[0-9]+)-(?P<stamp>[0-9]{8})$"
)


@dataclass(frozen=True)
class TagInfo:
    sdk_version: str
    timestamp: datetime
    historical: bool


def validate_sdk_version(value: str) -> str:
    """Return a strict public SDK version or raise a stable validation error."""

    if SDK_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("SDK version must use X.Y.Z")
    return value


def generate_tag(sdk_version: str, at: datetime | None = None) -> str:
    """Generate a UTC-minute Examples tag from a public SDK version."""

    version = validate_sdk_version(sdk_version)
    instant = at if at is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("release time must be timezone-aware")
    utc = instant.astimezone(timezone.utc)
    return f"v{version}-{utc:%Y%m%d%H%M}"


def parse_tag_timestamp(stamp: str, pattern: str, error: str) -> datetime:
    """Parse a tag timestamp without exposing runtime-specific parser text."""

    try:
        return datetime.strptime(stamp, pattern).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(error) from exc


def validate_tag(tag: str, *, allow_historical: bool = False) -> TagInfo:
    """Validate a current tag, or a historical tag only when explicitly allowed."""

    current = CURRENT_TAG_PATTERN.fullmatch(tag)
    if current is not None:
        timestamp = parse_tag_timestamp(
            current.group("stamp"),
            "%Y%m%d%H%M",
            "current release tag contains an impossible UTC minute",
        )
        return TagInfo(
            sdk_version=current.group("sdk"),
            timestamp=timestamp,
            historical=False,
        )

    historical = HISTORICAL_TAG_PATTERN.fullmatch(tag)
    if historical is not None and allow_historical:
        timestamp = parse_tag_timestamp(
            historical.group("stamp"),
            "%Y%m%d",
            "historical release tag contains an impossible UTC date",
        )
        return TagInfo(
            sdk_version=historical.group("sdk"),
            timestamp=timestamp,
            historical=True,
        )

    raise ValueError("tag does not match an allowed Examples release format")


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 instant without permitting a naive local time."""

    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("release time must use ISO-8601") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("release time must be timezone-aware")
    return instant


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="Generate and validate nxusKit Examples release tags."
    )
    commands = command_parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="generate a current UTC-minute tag")
    generate.add_argument("--sdk-version", required=True)
    generate.add_argument("--at", help="ISO-8601 aware time; defaults to now in UTC")

    validate = commands.add_parser("validate", help="validate an Examples release tag")
    validate.add_argument("--tag", required=True)
    validate.add_argument("--allow-historical", action="store_true")
    return command_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "generate":
            instant = parse_time(args.at) if args.at is not None else None
            print(generate_tag(args.sdk_version, instant))
            return 0
        info = validate_tag(args.tag, allow_historical=args.allow_historical)
        stamp_format = "%Y%m%d" if info.historical else "%Y%m%d%H%M"
        print(f"v{info.sdk_version}-{info.timestamp.strftime(stamp_format)}")
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
