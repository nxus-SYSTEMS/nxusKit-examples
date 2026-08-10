#!/usr/bin/env python3
"""Exact tracked-tree identity and public materialization helpers."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


REPO = Path(__file__).resolve().parents[1]
VECTOR = REPO / "conformance" / "fixtures" / "examples_publication_tree_v1.json"
TREE_DIGEST_ALGORITHM = "nxuskit-source-tree-sha256-v1"
TREE_DIGEST_MAGIC = b"nxuskit-source-tree-sha256\0v1\0"
SUPPORTED_ENTRIES = {
    ("100644", "blob"),
    ("100755", "blob"),
    ("120000", "blob"),
}
PUBLIC_TOP_LEVEL_FILES = (
    "README.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "LICENSE",
    "LICENSE-APACHE",
    "LICENSE-MIT",
    "NOTICE",
    "THIRD-PARTY-NOTICES.md",
    "ACKNOWLEDGEMENTS.md",
    ".gitignore",
    ".gitattributes",
)
PUBLIC_TOP_LEVEL_DIRECTORIES = (
    "examples",
    "conformance",
    "scripts",
    "tools",
    ".github",
)
PUBLIC_INPUT_PATHS = PUBLIC_TOP_LEVEL_FILES + PUBLIC_TOP_LEVEL_DIRECTORIES
PUBLIC_REMAPS = {
    ".github/workflows-public/ci.yml": ".github/workflows/ci.yml",
    ".github/workflows-public/release.yml": ".github/workflows/release.yml",
}
EXCLUDED_PUBLIC_SCRIPTS = {
    "scripts/sync-example-tiers-from-sdk.sh",
    "scripts/generate-content.py",
    "scripts/apply-content.py",
}
REQUIRED_PUBLIC_WORKFLOW_SOURCES = frozenset(PUBLIC_REMAPS)
FORBIDDEN_EXPORTED_WORKFLOWS = {
    ".github/workflows/publish-to-public.yml",
    ".github/workflows/publish-to-docs.yml",
    ".github/workflows/sdk-bundle-smoke.yml",
    ".github/workflows/sdk-integration-signal.yml",
    ".github/workflows/sdk-integration.yml",
}


class TreeIdentityError(RuntimeError):
    """Raised when a source tree cannot be identified safely."""


@dataclass(frozen=True)
class TreeEntry:
    """One exact Git-style tree entry."""

    path_bytes: bytes
    mode: str
    git_type: str
    content: bytes


def _validate_path(path_bytes: bytes) -> None:
    if not path_bytes or b"\0" in path_bytes or path_bytes.startswith(b"/"):
        raise TreeIdentityError(f"invalid tree path: {path_bytes!r}")
    parts = path_bytes.split(b"/")
    if any(part in {b"", b".", b".."} for part in parts):
        raise TreeIdentityError(
            f"tree path escapes or is not canonical: {path_bytes!r}"
        )


def validate_tree_entries(entries: Iterable[TreeEntry]) -> tuple[TreeEntry, ...]:
    """Validate and return entries in raw-path order."""

    validated = tuple(entries)
    if not validated:
        raise TreeIdentityError("source tree has no tracked entries")

    seen: set[bytes] = set()
    for entry in validated:
        _validate_path(entry.path_bytes)
        if entry.path_bytes in seen:
            raise TreeIdentityError(f"duplicate tree path: {entry.path_bytes!r}")
        seen.add(entry.path_bytes)
        if (entry.mode, entry.git_type) not in SUPPORTED_ENTRIES:
            raise TreeIdentityError(
                f"unsupported tree entry: mode={entry.mode!r}, type={entry.git_type!r}"
            )
        if not isinstance(entry.content, bytes):
            raise TreeIdentityError(
                f"tree entry content must be bytes: {entry.path_bytes!r}"
            )

    return tuple(sorted(validated, key=lambda item: item.path_bytes))


def canonical_tree_bytes(entries: Iterable[TreeEntry]) -> bytes:
    """Serialize entries using the frozen version-one byte format."""

    output = bytearray(TREE_DIGEST_MAGIC)
    for entry in validate_tree_entries(entries):
        output.extend(b"entry\0")
        output.extend(entry.mode.encode("ascii"))
        output.extend(b"\0")
        output.extend(entry.git_type.encode("ascii"))
        output.extend(b"\0")
        output.extend(len(entry.path_bytes).to_bytes(8, "big"))
        output.extend(entry.path_bytes)
        output.extend(len(entry.content).to_bytes(8, "big"))
        output.extend(entry.content)
    return bytes(output)


def source_tree_sha256(entries: Iterable[TreeEntry]) -> str:
    """Return the version-one exact tree SHA-256."""

    return hashlib.sha256(canonical_tree_bytes(entries)).hexdigest()


def _safe_tree_root(tree_root: str) -> bytes:
    encoded = tree_root.encode("utf-8")
    _validate_path(encoded)
    return encoded.rstrip(b"/")


def _git(repo: Path, args: list[str]) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TreeIdentityError(f"git command failed: {args[0]}") from exc
    return result.stdout


def _relative_tree_path(full_path: bytes, root: bytes) -> bytes:
    prefix = root + b"/"
    if not full_path.startswith(prefix):
        raise TreeIdentityError(f"tracked path is outside tree root: {full_path!r}")
    relative = full_path[len(prefix) :]
    _validate_path(relative)
    return relative


def _parse_ls_tree(repo: Path, root: bytes, source_ref: str) -> tuple[TreeEntry, ...]:
    output = _git(
        repo,
        [
            "ls-tree",
            "-rz",
            "--full-tree",
            source_ref,
            "--",
            root.decode("utf-8"),
        ],
    )
    entries: list[TreeEntry] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            header, full_path = record.split(b"\t", 1)
            mode_bytes, type_bytes, object_id = header.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            git_type = type_bytes.decode("ascii")
            object_text = object_id.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise TreeIdentityError("malformed git ls-tree record") from exc
        content = _git(repo, ["cat-file", "blob", object_text])
        entries.append(
            TreeEntry(
                path_bytes=_relative_tree_path(full_path, root),
                mode=mode,
                git_type=git_type,
                content=content,
            )
        )
    return validate_tree_entries(entries)


def _parse_ls_files(repo: Path, root: bytes) -> tuple[TreeEntry, ...]:
    output = _git(
        repo,
        ["ls-files", "-s", "-z", "--", root.decode("utf-8")],
    )
    entries: list[TreeEntry] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            header, full_path = record.split(b"\t", 1)
            mode_bytes, _object_id, stage = header.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise TreeIdentityError("malformed git ls-files record") from exc
        if stage != b"0":
            raise TreeIdentityError(f"unmerged tracked path: {full_path!r}")

        relative = _relative_tree_path(full_path, root)
        disk_path = repo / os.fsdecode(full_path)
        try:
            info = disk_path.lstat()
        except FileNotFoundError as exc:
            raise TreeIdentityError(f"tracked path is missing: {full_path!r}") from exc

        if mode == "120000":
            if not stat.S_ISLNK(info.st_mode):
                raise TreeIdentityError(
                    f"tracked path type differs from index: {full_path!r}"
                )
            content = os.readlink(disk_path).encode("utf-8", "surrogateescape")
        else:
            if not stat.S_ISREG(info.st_mode):
                raise TreeIdentityError(
                    f"tracked path type differs from index: {full_path!r}"
                )
            content = disk_path.read_bytes()
        entries.append(TreeEntry(relative, mode, "blob", content))
    return validate_tree_entries(entries)


def git_tree_entries(
    repo: Path, tree_root: str, source_ref: str | None
) -> tuple[TreeEntry, ...]:
    """Read an exact tree from a Git ref or tracked worktree/index."""

    resolved_repo = repo.resolve()
    root = _safe_tree_root(tree_root)
    if source_ref is None:
        return _parse_ls_files(resolved_repo, root)
    return _parse_ls_tree(resolved_repo, root, source_ref)


def git_index_tree_entries(repo: Path) -> tuple[TreeEntry, ...]:
    """Read every stage-zero entry and blob from a Git index."""

    resolved_repo = repo.resolve()
    output = _git(resolved_repo, ["ls-files", "-s", "-z"])
    entries: list[TreeEntry] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            header, path_bytes = record.split(b"\t", 1)
            mode_bytes, object_id, stage = header.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            object_text = object_id.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise TreeIdentityError("malformed git ls-files record") from exc
        if stage != b"0":
            raise TreeIdentityError(f"unmerged tracked path: {path_bytes!r}")
        _validate_path(path_bytes)
        entries.append(
            TreeEntry(
                path_bytes=path_bytes,
                mode=mode,
                git_type="blob",
                content=_git(resolved_repo, ["cat-file", "blob", object_text]),
            )
        )
    return validate_tree_entries(entries)


def digest_git_tree(repo: Path, tree_root: str, source_ref: str | None) -> str:
    """Return the canonical digest for a Git-backed example tree."""

    return source_tree_sha256(git_tree_entries(repo, tree_root, source_ref))


def _walk_filesystem(root: Path, relative: bytes = b"") -> list[TreeEntry]:
    entries: list[TreeEntry] = []
    try:
        children = sorted(os.scandir(root), key=lambda item: os.fsencode(item.name))
    except OSError as exc:
        raise TreeIdentityError(f"cannot read filesystem tree: {root}") from exc

    for child in children:
        name = os.fsencode(child.name)
        path_bytes = relative + (b"/" if relative else b"") + name
        try:
            info = child.stat(follow_symlinks=False)
        except OSError as exc:
            raise TreeIdentityError(
                f"cannot inspect filesystem entry: {path_bytes!r}"
            ) from exc
        child_path = Path(child.path)
        if stat.S_ISLNK(info.st_mode):
            content = os.readlink(child_path).encode("utf-8", "surrogateescape")
            entries.append(TreeEntry(path_bytes, "120000", "blob", content))
        elif stat.S_ISDIR(info.st_mode):
            entries.extend(_walk_filesystem(child_path, path_bytes))
        elif stat.S_ISREG(info.st_mode):
            mode = "100755" if info.st_mode & stat.S_IXUSR else "100644"
            entries.append(TreeEntry(path_bytes, mode, "blob", child_path.read_bytes()))
        else:
            raise TreeIdentityError(f"unsupported filesystem entry: {path_bytes!r}")
    return entries


def filesystem_tree_entries(root: Path) -> tuple[TreeEntry, ...]:
    """Read an exported filesystem tree without following symlinks."""

    if not root.is_dir() or root.is_symlink():
        raise TreeIdentityError(f"filesystem tree root is not a directory: {root}")
    return validate_tree_entries(_walk_filesystem(root))


def _decode_materialized_path(path_bytes: bytes) -> PurePosixPath:
    try:
        path = PurePosixPath(path_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise TreeIdentityError(f"tree path is not UTF-8: {path_bytes!r}") from exc
    _validate_path(path_bytes)
    return path


def _validate_symlink_target(path: PurePosixPath, content: bytes) -> str:
    try:
        target_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TreeIdentityError(f"symlink target is not UTF-8: {path}") from exc
    target = PurePosixPath(target_text)
    if target.is_absolute() or not target_text:
        raise TreeIdentityError(f"symlink target is absolute or empty: {path}")

    stack = list(path.parent.parts)
    for part in target.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not stack:
                raise TreeIdentityError(f"symlink target escapes tree: {path}")
            stack.pop()
        else:
            stack.append(part)
    return target_text


def materialize_entries(entries: Iterable[TreeEntry], destination: Path) -> None:
    """Write validated entries without following source or destination symlinks."""

    validated = validate_tree_entries(entries)
    decoded = [
        (entry, _decode_materialized_path(entry.path_bytes)) for entry in validated
    ]
    symlink_paths = {path for entry, path in decoded if entry.mode == "120000"}
    for _entry, path in decoded:
        if any(parent in symlink_paths for parent in path.parents):
            raise TreeIdentityError(f"tree path descends through symlink: {path}")
    symlink_targets = {
        path: _validate_symlink_target(path, entry.content)
        for entry, path in decoded
        if entry.mode == "120000"
    }

    if destination.exists() and any(destination.iterdir()):
        raise TreeIdentityError(
            f"materialization destination is not empty: {destination}"
        )
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()

    for entry, relative in decoded:
        target = destination / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            target.parent.resolve() != destination_root
            and destination_root not in target.parent.resolve().parents
        ):
            raise TreeIdentityError(
                f"materialization path escapes destination: {relative}"
            )
        if entry.mode == "120000":
            os.symlink(symlink_targets[relative], target)
            continue
        target.write_bytes(entry.content)
        target.chmod(0o755 if entry.mode == "100755" else 0o644)


def assert_no_public_untracked(repo: Path) -> None:
    """Reject non-ignored untracked bytes in any public input surface."""

    output = _git(
        repo.resolve(),
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *PUBLIC_INPUT_PATHS,
        ],
    )
    paths = sorted(path for path in output.split(b"\0") if path)
    if paths:
        rendered = ", ".join(repr(path) for path in paths)
        raise TreeIdentityError(
            f"non-ignored untracked public input path(s): {rendered}"
        )


def _resolve_commit(repo: Path, source_ref: str) -> str:
    if not source_ref:
        raise TreeIdentityError("source ref is required")
    resolved = _git(
        repo.resolve(), ["rev-parse", "--verify", f"{source_ref}^{{commit}}"]
    )
    try:
        commit = resolved.strip().decode("ascii")
    except UnicodeDecodeError as exc:
        raise TreeIdentityError("resolved commit is not ASCII") from exc
    if len(commit) != 40 or any(
        character not in "0123456789abcdef" for character in commit
    ):
        raise TreeIdentityError("resolved source ref is not a full commit SHA")
    return commit


def _public_destination(path: bytes) -> bytes | None:
    try:
        text = path.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TreeIdentityError(f"public input path is not UTF-8: {path!r}") from exc

    remapped = PUBLIC_REMAPS.get(text)
    if remapped is not None:
        return remapped.encode("utf-8")
    if text in PUBLIC_TOP_LEVEL_FILES:
        return path
    if not any(text.startswith(f"{root}/") for root in PUBLIC_TOP_LEVEL_DIRECTORIES):
        return None
    if text in EXCLUDED_PUBLIC_SCRIPTS:
        return None
    if text.startswith(".github/workflows/") or text.startswith(
        ".github/workflows-public/"
    ):
        return None
    return path


def _project_public_entries(repo: Path, source_ref: str) -> tuple[TreeEntry, ...]:
    commit = _resolve_commit(repo, source_ref)
    output = _git(repo.resolve(), ["ls-tree", "-rz", "--full-tree", "-r", commit])
    projected: list[TreeEntry] = []
    destinations: dict[bytes, bytes] = {}
    seen_sources: set[str] = set()
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            header, full_path = record.split(b"\t", 1)
            mode_bytes, type_bytes, object_id = header.split(b" ", 2)
            mode = mode_bytes.decode("ascii")
            git_type = type_bytes.decode("ascii")
            object_text = object_id.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise TreeIdentityError("malformed git ls-tree record") from exc
        try:
            source_text = full_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TreeIdentityError(
                f"tracked public source path is not UTF-8: {full_path!r}"
            ) from exc
        seen_sources.add(source_text)
        destination = _public_destination(full_path)
        if destination is None:
            continue
        existing = destinations.get(destination)
        if existing is not None:
            raise TreeIdentityError(
                f"duplicate public destination {destination!r} from {existing!r} and {full_path!r}"
            )
        destinations[destination] = full_path
        if (mode, git_type) not in SUPPORTED_ENTRIES:
            projected.append(TreeEntry(destination, mode, git_type, b""))
            continue
        content = _git(repo.resolve(), ["cat-file", "blob", object_text])
        projected.append(TreeEntry(destination, mode, git_type, content))

    missing_workflows = sorted(REQUIRED_PUBLIC_WORKFLOW_SOURCES - seen_sources)
    if missing_workflows:
        raise TreeIdentityError(
            f"missing public workflow source(s): {missing_workflows}"
        )
    return validate_tree_entries(projected)


def materialize_public_export(repo: Path, output: Path, source_ref: str) -> None:
    """Materialize the declarative public projection from one exact commit."""

    if output.is_symlink() or (
        output.exists() and (not output.is_dir() or any(output.iterdir()))
    ):
        raise TreeIdentityError(f"public export output is not empty: {output}")
    assert_no_public_untracked(repo)
    entries = _project_public_entries(repo, source_ref)
    materialize_entries(entries, output)


def _load_publication_generator():
    path = REPO / "scripts" / "generate-examples-publication-selection.py"
    spec = importlib.util.spec_from_file_location(
        "publication_selection_generator", path
    )
    if spec is None or spec.loader is None:
        raise TreeIdentityError("cannot load publication selection generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def attest_public_export(export_root: Path) -> dict[str, object]:
    """Attest exact selected example trees and public workflow boundaries."""

    selection_path = export_root / "conformance" / "examples_publication_selection.json"
    try:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TreeIdentityError("cannot read exported publication selection") from exc
    if not isinstance(selection, dict):
        raise TreeIdentityError("exported publication selection must be an object")

    workflows_public = export_root / ".github" / "workflows-public"
    if workflows_public.exists():
        raise TreeIdentityError("source-only public workflow directory leaked")
    for relative in sorted(FORBIDDEN_EXPORTED_WORKFLOWS):
        if (export_root / relative).exists():
            raise TreeIdentityError(f"internal workflow leaked: {relative}")
    for name in ("ci.yml", "release.yml"):
        if not (export_root / ".github" / "workflows" / name).is_file():
            raise TreeIdentityError(f"exported public workflow is missing: {name}")

    generator = _load_publication_generator()
    try:
        digests = generator.attest_exported_selection(export_root, selection)
    except generator.PublicationError as exc:
        raise TreeIdentityError(str(exc)) from exc
    return {
        "ok": True,
        "selected_examples_count": len(digests),
        "source_tree_sha256_by_example": dict(sorted(digests.items())),
    }


def attest_staged_export(repo: Path, export_root: Path) -> dict[str, object]:
    """Prove that a destination Git index exactly represents one export."""

    staged_entries = git_index_tree_entries(repo)
    export_entries = filesystem_tree_entries(export_root.resolve())
    if staged_entries != export_entries:
        raise TreeIdentityError("staged public tree does not match attested export")
    return {"ok": True, "tracked_paths_count": len(staged_entries)}


def run_self_test() -> dict[str, object]:
    """Validate the portable canonical tree vector."""

    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    if vector.get("algorithm") != TREE_DIGEST_ALGORITHM:
        raise TreeIdentityError("tree vector algorithm does not match implementation")
    entries = tuple(
        TreeEntry(
            path_bytes=item["path"].encode("utf-8"),
            mode=item["mode"],
            git_type=item["git_type"],
            content=item["content_utf8"].encode("utf-8"),
        )
        for item in vector["entries"]
    )
    digest = source_tree_sha256(entries)
    if digest != vector.get("source_tree_sha256"):
        raise TreeIdentityError("tree vector digest does not match implementation")
    return {
        "algorithm": TREE_DIGEST_ALGORITHM,
        "ok": True,
        "source_tree_sha256": digest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test", help="Validate the canonical tree vector.")
    materialize = subparsers.add_parser(
        "materialize-public-export",
        help="Materialize the public projection from an exact Git commit.",
    )
    materialize.add_argument("--repo", type=Path, default=REPO)
    materialize.add_argument("--source-ref", required=True)
    materialize.add_argument("--output", type=Path, required=True)
    attest = subparsers.add_parser(
        "attest-public-export", help="Attest a filtered public export."
    )
    attest.add_argument("--export-root", type=Path, required=True)
    staged = subparsers.add_parser(
        "attest-staged-export",
        help="Attest that a Git index exactly represents a public export.",
    )
    staged.add_argument("--repo", type=Path, required=True)
    staged.add_argument("--export-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "self-test":
            print(json.dumps(run_self_test(), indent=2, sort_keys=True))
            return 0
        if args.command == "materialize-public-export":
            materialize_public_export(args.repo, args.output, args.source_ref)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "output": str(args.output),
                        "source_ref": _resolve_commit(args.repo, args.source_ref),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "attest-public-export":
            print(
                json.dumps(
                    attest_public_export(args.export_root), indent=2, sort_keys=True
                )
            )
            return 0
        if args.command == "attest-staged-export":
            print(
                json.dumps(
                    attest_staged_export(args.repo, args.export_root),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        raise TreeIdentityError(f"unsupported command: {args.command}")
    except (KeyError, TypeError, TreeIdentityError, UnicodeError) as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
