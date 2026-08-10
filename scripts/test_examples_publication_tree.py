#!/usr/bin/env python3
"""Regression tests for exact Examples publication tree identity."""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
VECTOR = REPO / "conformance" / "fixtures" / "examples_publication_tree_v1.json"
GENERATOR = REPO / "scripts" / "generate-examples-publication-selection.py"
WORKFLOW_CHECKER = REPO / "scripts" / "check_examples_publication_workflow.py"
sys.path.insert(0, str(SCRIPTS))

import examples_publication_tree as tree_module  # noqa: E402

from examples_publication_tree import (  # noqa: E402
    TreeEntry,
    TreeIdentityError,
    digest_git_tree,
    filesystem_tree_entries,
    git_tree_entries,
    materialize_entries,
    source_tree_sha256,
)


def fixture_entries() -> tuple[TreeEntry, ...]:
    vector = json.loads(VECTOR.read_text(encoding="utf-8"))
    return tuple(
        TreeEntry(
            path_bytes=item["path"].encode("utf-8"),
            mode=item["mode"],
            git_type=item["git_type"],
            content=item["content_utf8"].encode("utf-8"),
        )
        for item in vector["entries"]
    )


def load_publication_generator():
    spec = importlib.util.spec_from_file_location(
        "publication_selection_generator", GENERATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load publication selection generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_publication_workflow_checker():
    spec = importlib.util.spec_from_file_location(
        "examples_publication_workflow_checker", WORKFLOW_CHECKER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load publication workflow checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CanonicalTreeIdentityTests(unittest.TestCase):
    def test_canonical_vector_matches_frozen_digest(self) -> None:
        vector = json.loads(VECTOR.read_text(encoding="utf-8"))

        self.assertEqual(
            source_tree_sha256(reversed(fixture_entries())),
            vector["source_tree_sha256"],
        )

    def test_entry_order_does_not_change_digest(self) -> None:
        entries = fixture_entries()

        self.assertEqual(source_tree_sha256(entries), source_tree_sha256(entries[::-1]))

    def test_exact_byte_change_changes_digest(self) -> None:
        entries = fixture_entries()
        changed = (replace(entries[0], content=b"# Damo\n"), *entries[1:])

        self.assertNotEqual(source_tree_sha256(entries), source_tree_sha256(changed))

    def test_mode_change_changes_digest(self) -> None:
        entries = fixture_entries()
        changed = (replace(entries[0], mode="100755"), *entries[1:])

        self.assertNotEqual(source_tree_sha256(entries), source_tree_sha256(changed))

    def test_path_rename_changes_digest(self) -> None:
        entries = fixture_entries()
        changed = (replace(entries[0], path_bytes=b"README.txt"), *entries[1:])

        self.assertNotEqual(source_tree_sha256(entries), source_tree_sha256(changed))

    def test_addition_and_deletion_change_digest(self) -> None:
        entries = fixture_entries()
        added = (
            *entries,
            TreeEntry(b"notes.txt", "100644", "blob", b"notes\n"),
        )

        self.assertNotEqual(source_tree_sha256(entries), source_tree_sha256(added))
        self.assertNotEqual(
            source_tree_sha256(entries), source_tree_sha256(entries[:-1])
        )

    def test_duplicate_path_fails_closed(self) -> None:
        entries = fixture_entries()

        with self.assertRaisesRegex(TreeIdentityError, "duplicate tree path"):
            source_tree_sha256((*entries, entries[0]))

    def test_unsupported_mode_and_type_fail_closed(self) -> None:
        entries = fixture_entries()

        with self.assertRaisesRegex(TreeIdentityError, "unsupported tree entry"):
            source_tree_sha256((replace(entries[0], mode="160000"),))
        with self.assertRaisesRegex(TreeIdentityError, "unsupported tree entry"):
            source_tree_sha256((replace(entries[0], git_type="commit"),))


class GitTreeReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="publication-tree-git-")
        self.repo = Path(self.temp.name)
        self.tree_root = self.repo / "examples" / "patterns" / "demo"
        (self.tree_root / "bin").mkdir(parents=True)
        (self.tree_root / "README.md").write_text("# Demo\n", encoding="utf-8")
        run = self.tree_root / "bin" / "run.sh"
        run.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        run.chmod(0o755)
        os.symlink("README.md", self.tree_root / "latest")
        (self.repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Tree Test")
        self.git("config", "user.email", "tree-test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.commit_sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.relative_root = "examples/patterns/demo"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_exact_ref_reads_committed_blobs_not_modified_worktree(self) -> None:
        before = digest_git_tree(self.repo, self.relative_root, self.commit_sha)
        (self.tree_root / "README.md").write_text("# Damo\n", encoding="utf-8")

        self.assertNotEqual(
            before, digest_git_tree(self.repo, self.relative_root, None)
        )
        self.assertEqual(
            before, digest_git_tree(self.repo, self.relative_root, self.commit_sha)
        )

    def test_staged_addition_and_deletion_change_worktree_digest(self) -> None:
        before = digest_git_tree(self.repo, self.relative_root, None)
        (self.tree_root / "new.txt").write_text("new\n", encoding="utf-8")
        self.git("add", str(self.tree_root / "new.txt"))
        after_add = digest_git_tree(self.repo, self.relative_root, None)
        self.assertNotEqual(before, after_add)

        (self.tree_root / "README.md").unlink()
        self.git("add", "-u", self.relative_root)
        self.assertNotEqual(
            after_add, digest_git_tree(self.repo, self.relative_root, None)
        )

    def test_staged_rename_and_mode_change_change_worktree_digest(self) -> None:
        before = digest_git_tree(self.repo, self.relative_root, None)
        self.git(
            "mv",
            f"{self.relative_root}/README.md",
            f"{self.relative_root}/README.txt",
        )
        after_rename = digest_git_tree(self.repo, self.relative_root, None)
        self.assertNotEqual(before, after_rename)

        self.git("update-index", "--chmod=-x", f"{self.relative_root}/bin/run.sh")
        self.assertNotEqual(
            after_rename, digest_git_tree(self.repo, self.relative_root, None)
        )

    def test_ignored_and_nonignored_untracked_files_do_not_enter_digest(self) -> None:
        before = digest_git_tree(self.repo, self.relative_root, None)
        cache = self.tree_root / "__pycache__"
        cache.mkdir()
        (cache / "x.pyc").write_bytes(b"ignored bytecode")
        (self.tree_root / "UNTRACKED.md").write_text("untracked\n", encoding="utf-8")

        self.assertEqual(before, digest_git_tree(self.repo, self.relative_root, None))

    def test_missing_tracked_worktree_entry_fails_closed(self) -> None:
        (self.tree_root / "README.md").unlink()

        with self.assertRaisesRegex(TreeIdentityError, "tracked path is missing"):
            digest_git_tree(self.repo, self.relative_root, None)

    def test_materialized_entries_match_git_and_filesystem_digest(self) -> None:
        entries = git_tree_entries(self.repo, self.relative_root, self.commit_sha)
        destination = self.repo / "materialized"
        materialize_entries(entries, destination)

        self.assertTrue((destination / "latest").is_symlink())
        self.assertEqual(os.readlink(destination / "latest"), "README.md")
        self.assertEqual(
            source_tree_sha256(entries),
            source_tree_sha256(filesystem_tree_entries(destination)),
        )

    def test_absolute_and_escaping_symlinks_fail_before_materialization(self) -> None:
        for target in (b"/etc/passwd", b"../../secret"):
            with self.subTest(target=target):
                entry = TreeEntry(b"links/outside", "120000", "blob", target)
                with self.assertRaisesRegex(TreeIdentityError, "symlink target"):
                    materialize_entries((entry,), self.repo / "unsafe-output")

    def test_destination_path_escape_fails_before_materialization(self) -> None:
        entry = TreeEntry(b"../outside", "100644", "blob", b"blocked\n")

        with self.assertRaisesRegex(TreeIdentityError, "tree path escapes"):
            materialize_entries((entry,), self.repo / "unsafe-output")


class PublicationSelectionTreeDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_publication_generator()
        self.temp = tempfile.TemporaryDirectory(prefix="publication-selection-tree-")
        self.repo = Path(self.temp.name)
        self.tree_root = self.repo / "examples" / "patterns" / "demo"
        self.tree_root.mkdir(parents=True)
        (self.tree_root / "main.py").write_text("print('one')\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Selection Test")
        self.git("config", "user.email", "selection-test@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.commit_sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.digest = digest_git_tree(
            self.repo, "examples/patterns/demo", self.commit_sha
        )
        self.manifest = {
            "$schema": "./harness/schema.json",
            "version": "5.1.0",
            "description": "test manifest",
            "examples": [
                {
                    "name": "demo",
                    "description": "Tree identity fixture",
                    "category": "patterns",
                    "required": True,
                    "scenario": "Test publication identity",
                    "real_world_application": "Publication testing",
                    "tech_tags": ["LLM"],
                    "languages": ["python"],
                    "implementations": {"python": "examples/patterns/demo/main.py"},
                    "tier": "community",
                    "content_hash": "a" * 64,
                    "source_tree_sha256": self.digest,
                }
            ],
        }
        self.ledger = {
            "schema_version": "1.0.0",
            "ledger_type": "test-publication-ledger",
            "policy": {},
            "public_channels": ["repo", "docs", "celerat", "website"],
            "entries": [
                {
                    "example_id": "demo",
                    "publication_status": "approved",
                    "public_channels": ["repo", "docs", "celerat", "website"],
                    "approved_release": "test-release",
                    "approved_content_hash": "a" * 64,
                    "approved_source_tree_sha256": self.digest,
                    "approved_source_ref": {
                        "kind": "current_source",
                        "ref": "conformance/examples_manifest.json",
                        "public_safe": True,
                    },
                    "public_clearance": {
                        "state": "approved_public",
                        "authority": "leadership_team",
                        "scope": ["repo", "docs", "celerat", "website"],
                        "profile": "production_ready",
                    },
                    "current_content_hash": "a" * 64,
                    "current_source_tree_sha256": self.digest,
                    "current_changes_public_ready": True,
                }
            ],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def build(self, *, require_tree_digests: bool = True):
        return self.generator.build_selection(
            self.manifest,
            self.ledger,
            repo=self.repo,
            source_ref=None,
            require_tree_digests=require_tree_digests,
        )

    def test_strict_selection_carries_exact_tree_receipts(self) -> None:
        selection = self.build()
        record = selection["publication_selection"]["approved_examples"][0]

        self.assertEqual(record["approved_source_tree_sha256"], self.digest)
        self.assertEqual(record["selected_source"]["source_tree_sha256"], self.digest)
        self.assertEqual(record["selected_source"]["content_hash"], "a" * 64)
        self.assertTrue(
            selection["publication_selection"]["approval_policy"][
                "tree_digest_authoritative"
            ]
        )

    def test_same_sloc_substitution_fails_closed(self) -> None:
        (self.tree_root / "main.py").write_text("print('two')\n", encoding="utf-8")

        with self.assertRaisesRegex(
            self.generator.PublicationError, "source_tree_sha256 mismatch"
        ):
            self.build()

    def test_tracked_addition_fails_closed(self) -> None:
        (self.tree_root / "added.py").write_text("pass\n", encoding="utf-8")
        self.git("add", "examples/patterns/demo/added.py")

        with self.assertRaisesRegex(
            self.generator.PublicationError, "source_tree_sha256 mismatch"
        ):
            self.build()

    def test_tracked_deletion_fails_closed(self) -> None:
        (self.tree_root / "main.py").unlink()
        self.git("add", "-u", "examples/patterns/demo")

        with self.assertRaisesRegex(
            self.generator.PublicationError, "source tree has no tracked entries"
        ):
            self.build()

    def test_tracked_mode_change_fails_closed(self) -> None:
        self.git("update-index", "--chmod=+x", "examples/patterns/demo/main.py")

        with self.assertRaisesRegex(
            self.generator.PublicationError, "source_tree_sha256 mismatch"
        ):
            self.build()

    def test_missing_tree_digest_fields_fail_closed(self) -> None:
        cases = (
            (self.manifest["examples"][0], "source_tree_sha256"),
            (self.ledger["entries"][0], "approved_source_tree_sha256"),
            (self.ledger["entries"][0], "current_source_tree_sha256"),
        )
        for mapping, field in cases:
            with self.subTest(field=field):
                value = mapping.pop(field)
                try:
                    with self.assertRaisesRegex(self.generator.PublicationError, field):
                        self.build()
                finally:
                    mapping[field] = value

    def test_malformed_tree_digest_fails_closed(self) -> None:
        self.manifest["examples"][0]["source_tree_sha256"] = "ABC"

        with self.assertRaisesRegex(
            self.generator.PublicationError, "source_tree_sha256"
        ):
            self.build()

    def test_stale_current_tree_digest_fails_closed(self) -> None:
        self.ledger["entries"][0]["current_source_tree_sha256"] = "b" * 64

        with self.assertRaisesRegex(
            self.generator.PublicationError, "current_source_tree_sha256 mismatch"
        ):
            self.build()

    def test_approved_tree_digest_mismatch_fails_closed(self) -> None:
        self.ledger["entries"][0]["approved_source_tree_sha256"] = "b" * 64

        with self.assertRaisesRegex(
            self.generator.PublicationError, "approved_source_tree_sha256 mismatch"
        ):
            self.build()

    def test_compatibility_mode_preserves_legacy_content_hash(self) -> None:
        del self.manifest["examples"][0]["source_tree_sha256"]
        del self.ledger["entries"][0]["approved_source_tree_sha256"]
        del self.ledger["entries"][0]["current_source_tree_sha256"]

        selection = self.build(require_tree_digests=False)

        self.assertEqual(selection["examples"][0]["content_hash"], "a" * 64)
        self.assertFalse(
            selection["publication_selection"]["approval_policy"][
                "tree_digest_authoritative"
            ]
        )


class LocalTreePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_publication_generator()
        self.temp = tempfile.TemporaryDirectory(prefix="publication-local-tree-")
        self.repo = Path(self.temp.name)
        self.current_root = self.repo / "examples" / "patterns" / "demo"
        self.approved_root = self.repo / "approved" / "demo"
        self.current_root.mkdir(parents=True)
        self.approved_root.mkdir(parents=True)
        (self.current_root / "WIP_SENTINEL.txt").write_text(
            "unapproved current source\n", encoding="utf-8"
        )
        approved_program = self.approved_root / "main.py"
        approved_program.write_text("print('approved')\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Local Tree Test")
        self.git("config", "user.email", "local-tree@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.current_digest = digest_git_tree(self.repo, "examples/patterns/demo", None)
        self.approved_digest = digest_git_tree(self.repo, "approved/demo", None)
        self.approved_manifest_entry = self.example(
            content_hash="a" * 64,
            source_tree_sha256=self.approved_digest,
        )
        self.manifest = {
            "version": "5.1.0",
            "examples": [
                self.example(
                    content_hash="b" * 64,
                    source_tree_sha256=self.current_digest,
                )
            ],
        }
        self.ledger = {
            "schema_version": "1.0.0",
            "entries": [
                {
                    "example_id": "demo",
                    "publication_status": "approved",
                    "public_channels": ["repo", "docs", "celerat", "website"],
                    "approved_release": "test-release",
                    "approved_content_hash": "a" * 64,
                    "approved_source_tree_sha256": self.approved_digest,
                    "approved_source_ref": {
                        "kind": "local_tree",
                        "public_safe": True,
                        "manifest_entry": self.approved_manifest_entry,
                        "manifest_entry_sha256": self.generator.json_sha256(
                            self.approved_manifest_entry
                        ),
                        "example_dir": "approved/demo",
                        "source_tree_sha256": self.approved_digest,
                        "example_tree_sha256": "f" * 64,
                    },
                    "public_clearance": {
                        "state": "approved_public",
                        "authority": "leadership_team",
                        "scope": ["repo", "docs", "celerat", "website"],
                        "profile": "production_ready",
                    },
                    "current_content_hash": "b" * 64,
                    "current_source_tree_sha256": self.current_digest,
                    "current_changes_public_ready": False,
                }
            ],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @staticmethod
    def example(*, content_hash: str, source_tree_sha256: str) -> dict[str, object]:
        return {
            "name": "demo",
            "description": "Held exact source fixture",
            "category": "patterns",
            "required": True,
            "scenario": "Test held source",
            "real_world_application": "Publication testing",
            "tech_tags": ["LLM"],
            "languages": ["python"],
            "implementations": {"python": "examples/patterns/demo/main.py"},
            "tier": "community",
            "content_hash": content_hash,
            "source_tree_sha256": source_tree_sha256,
        }

    def build(self):
        return self.generator.build_selection(
            self.manifest,
            self.ledger,
            repo=self.repo,
            source_ref=None,
            require_tree_digests=True,
        )

    def test_selection_returns_approved_manifest_and_exact_digest(self) -> None:
        selection = self.build()
        record = selection["publication_selection"]["approved_examples"][0]

        self.assertEqual(selection["examples"][0], self.approved_manifest_entry)
        self.assertEqual(record["approved_source_tree_sha256"], self.approved_digest)
        self.assertEqual(
            record["selected_source"]["source_tree_sha256"],
            self.approved_digest,
        )

    def test_same_sloc_approved_tree_mutation_fails_closed(self) -> None:
        (self.approved_root / "main.py").write_text(
            "print('changed!')\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(
            self.generator.PublicationError, "source_tree_sha256 mismatch"
        ):
            self.build()

    def test_tracked_addition_deletion_and_mode_change_fail_closed(self) -> None:
        mutations = ("addition", "deletion", "mode")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                if mutation == "addition":
                    added = self.approved_root / "added.py"
                    added.write_text("pass\n", encoding="utf-8")
                    self.git("add", "approved/demo/added.py")
                elif mutation == "deletion":
                    (self.approved_root / "main.py").unlink()
                    self.git("add", "-u", "approved/demo")
                else:
                    self.git("update-index", "--chmod=+x", "approved/demo/main.py")
                try:
                    with self.assertRaisesRegex(
                        self.generator.PublicationError,
                        "source_tree_sha256 mismatch|source tree has no tracked entries",
                    ):
                        self.build()
                finally:
                    self.git("reset", "--hard", "-q", "HEAD")

    def test_missing_authoritative_digest_rejects_legacy_only_receipt(self) -> None:
        del self.ledger["entries"][0]["approved_source_ref"]["source_tree_sha256"]

        with self.assertRaisesRegex(
            self.generator.PublicationError,
            "approved_source_ref.source_tree_sha256",
        ):
            self.build()

    def test_stale_embedded_manifest_hash_fails_closed(self) -> None:
        self.ledger["entries"][0]["approved_source_ref"]["manifest_entry_sha256"] = (
            "0" * 64
        )

        with self.assertRaisesRegex(
            self.generator.PublicationError, "manifest_entry_sha256 mismatch"
        ):
            self.build()

    def test_unavailable_approved_source_path_fails_closed(self) -> None:
        self.ledger["entries"][0]["approved_source_ref"]["example_dir"] = (
            "approved/missing"
        )

        with self.assertRaisesRegex(
            self.generator.PublicationError,
            "source tree has no tracked entries",
        ):
            self.build()

    def test_materialization_excludes_wip_and_ignored_bytes_and_attests(self) -> None:
        ignored = self.approved_root / "__pycache__"
        ignored.mkdir()
        (ignored / "hidden.pyc").write_bytes(b"ignored")
        selection = self.build()
        export_root = self.repo / "export"
        target = export_root / "examples" / "patterns" / "demo"
        target.mkdir(parents=True)
        (target / "WIP_SENTINEL.txt").write_text("must disappear\n", encoding="utf-8")

        self.generator.copy_approved_variant_trees(
            export_root,
            selection,
            self.ledger,
            repo=self.repo,
            source_ref=None,
        )
        receipt = self.generator.attest_exported_selection(export_root, selection)

        self.assertFalse((target / "WIP_SENTINEL.txt").exists())
        self.assertFalse((target / "__pycache__").exists())
        self.assertEqual((target / "main.py").read_text(), "print('approved')\n")
        self.assertEqual(receipt, {"demo": self.approved_digest})


class PublicMaterializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="publication-materializer-")
        self.repo = Path(self.temp.name)
        self.output = self.repo / "proof-output"
        for name in ("README.md", "LICENSE", ".gitignore", ".gitattributes"):
            (self.repo / name).write_text(f"{name}\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            "__pycache__/\n.venv/\n*.pyc\nproof-output/\n", encoding="utf-8"
        )
        example = self.repo / "examples" / "patterns" / "demo"
        example.mkdir(parents=True)
        (example / "main.py").write_text("print('public')\n", encoding="utf-8")
        os.symlink("main.py", example / "latest")
        scripts = self.repo / "scripts"
        scripts.mkdir()
        (scripts / "keep.py").write_text("print('keep')\n", encoding="utf-8")
        for name in (
            "sync-example-tiers-from-sdk.sh",
            "generate-content.py",
            "apply-content.py",
        ):
            (scripts / name).write_text("excluded\n", encoding="utf-8")
        tools = self.repo / "tools"
        tools.mkdir()
        executable = tools / "public-tool.sh"
        executable.write_text("#!/bin/sh\necho public\n", encoding="utf-8")
        executable.chmod(0o755)
        workflows = self.repo / ".github" / "workflows"
        public_workflows = self.repo / ".github" / "workflows-public"
        workflows.mkdir(parents=True)
        public_workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("private-ci\n", encoding="utf-8")
        for name in (
            "publish-to-public.yml",
            "publish-to-docs.yml",
            "sdk-bundle-smoke.yml",
        ):
            (workflows / name).write_text("private-workflow\n", encoding="utf-8")
        (public_workflows / "ci.yml").write_text("public-ci\n", encoding="utf-8")
        (public_workflows / "release.yml").write_text(
            "public-release\n", encoding="utf-8"
        )
        (self.repo / "private").mkdir()
        (self.repo / "private" / "sentinel.txt").write_text(
            "never public\n", encoding="utf-8"
        )
        (self.repo / "conformance").mkdir()
        digest = source_tree_sha256(filesystem_tree_entries(example))
        selection = {
            "version": "test",
            "examples": [
                {
                    "name": "demo",
                    "category": "patterns",
                    "content_hash": "a" * 64,
                }
            ],
            "publication_selection": {
                "approval_policy": {"tree_digest_authoritative": True},
                "approved_examples": [
                    {
                        "example_id": "demo",
                        "approved_source_tree_sha256": digest,
                        "selected_source": {
                            "kind": "current_source",
                            "content_hash": "a" * 64,
                            "source_tree_sha256": digest,
                        },
                    }
                ],
            },
        }
        (self.repo / "conformance" / "examples_publication_selection.json").write_text(
            json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.git("init", "-q")
        self.git("config", "user.name", "Materializer Test")
        self.git("config", "user.email", "materializer@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.commit_sha = self.git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def materialize(self, source_ref: str | None = None) -> None:
        tree_module.materialize_public_export(
            self.repo,
            self.output,
            source_ref or self.commit_sha,
        )

    def test_projection_is_tracked_public_only_and_remaps_workflows(self) -> None:
        self.materialize()

        self.assertEqual(
            (self.output / ".github" / "workflows" / "ci.yml").read_text(),
            "public-ci\n",
        )
        self.assertEqual(
            (self.output / ".github" / "workflows" / "release.yml").read_text(),
            "public-release\n",
        )
        self.assertFalse((self.output / ".github" / "workflows-public").exists())
        self.assertFalse(
            (self.output / ".github" / "workflows" / "publish-to-public.yml").exists()
        )
        self.assertFalse((self.output / "private").exists())
        for name in (
            "sync-example-tiers-from-sdk.sh",
            "generate-content.py",
            "apply-content.py",
        ):
            self.assertFalse((self.output / "scripts" / name).exists())
        self.assertEqual(
            (self.output / "scripts" / "keep.py").read_text(), "print('keep')\n"
        )
        self.assertTrue(
            (self.output / "examples" / "patterns" / "demo" / "latest").is_symlink()
        )
        self.assertTrue(
            (self.output / "tools" / "public-tool.sh").stat().st_mode & 0o100
        )

    def test_exact_ref_ignores_modified_tracked_worktree_bytes(self) -> None:
        (self.repo / "README.md").write_text("modified worktree\n", encoding="utf-8")

        self.materialize()

        self.assertEqual((self.output / "README.md").read_text(), "README.md\n")

    def test_ignored_files_never_enter_or_block_output(self) -> None:
        example = self.repo / "examples" / "patterns" / "demo"
        cache = example / "__pycache__"
        cache.mkdir()
        (cache / "x.pyc").write_bytes(b"ignored")
        (example / ".venv").mkdir()
        (example / ".venv" / "ignored.pyc").write_bytes(b"ignored")

        self.materialize()

        self.assertFalse(
            (self.output / "examples" / "patterns" / "demo" / "__pycache__").exists()
        )
        self.assertFalse(
            (self.output / "examples" / "patterns" / "demo" / ".venv").exists()
        )

    def test_nonignored_untracked_public_input_fails_before_output(self) -> None:
        (self.repo / "examples" / "patterns" / "demo" / "UNTRACKED.md").write_text(
            "blocked\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(TreeIdentityError, "non-ignored untracked"):
            self.materialize()
        self.assertFalse(self.output.exists())

    def test_untracked_outside_public_inputs_is_ignored(self) -> None:
        (self.repo / "private" / "untracked.txt").write_text(
            "not projected\n", encoding="utf-8"
        )

        self.materialize()

        self.assertFalse((self.output / "private").exists())

    def test_unsupported_entry_and_escaping_symlink_fail_closed(self) -> None:
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{self.commit_sha},examples/patterns/demo/gitlink",
        )
        self.git("commit", "-qm", "add unsupported gitlink")
        with self.assertRaisesRegex(TreeIdentityError, "unsupported tree entry"):
            self.materialize(self.git("rev-parse", "HEAD").stdout.strip())
        self.assertFalse(self.output.exists())

        self.git("reset", "--hard", "-q", self.commit_sha)
        os.symlink(
            "../../../../secret",
            self.repo / "examples" / "patterns" / "demo" / "escape",
        )
        self.git("add", "examples/patterns/demo/escape")
        self.git("commit", "-qm", "add escaping symlink")
        with self.assertRaisesRegex(TreeIdentityError, "symlink target escapes"):
            self.materialize(self.git("rev-parse", "HEAD").stdout.strip())
        self.assertFalse(self.output.exists())

    def test_missing_workflow_duplicate_destination_nonempty_and_bad_ref_fail(
        self,
    ) -> None:
        self.git("rm", "-q", ".github/workflows-public/release.yml")
        self.git("commit", "-qm", "remove required workflow")
        with self.assertRaisesRegex(
            TreeIdentityError, "missing public workflow source"
        ):
            self.materialize(self.git("rev-parse", "HEAD").stdout.strip())
        self.assertFalse(self.output.exists())

        self.git("reset", "--hard", "-q", self.commit_sha)
        with mock.patch.dict(
            tree_module.PUBLIC_REMAPS,
            {".github/workflows-public/release.yml": ".github/workflows/ci.yml"},
        ):
            with self.assertRaisesRegex(
                TreeIdentityError, "duplicate public destination"
            ):
                self.materialize()
        self.assertFalse(self.output.exists())

        self.output.mkdir()
        (self.output / "sentinel").write_text("preserve\n", encoding="utf-8")
        with self.assertRaisesRegex(TreeIdentityError, "output is not empty"):
            self.materialize()
        self.assertEqual((self.output / "sentinel").read_text(), "preserve\n")

        self.output.unlink() if self.output.is_file() else None
        with self.assertRaisesRegex(TreeIdentityError, "git command failed"):
            tree_module.materialize_public_export(
                self.repo, self.repo / "bad-ref-output", "0" * 40
            )
        self.assertFalse((self.repo / "bad-ref-output").exists())

    def test_public_export_attestation_reports_selected_digest(self) -> None:
        self.materialize()

        receipt = tree_module.attest_public_export(self.output)

        self.assertEqual(receipt["selected_examples_count"], 1)
        self.assertEqual(set(receipt["source_tree_sha256_by_example"]), {"demo"})


class TreeDigestMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_publication_generator()
        self.temp = tempfile.TemporaryDirectory(prefix="publication-migration-")
        self.repo = Path(self.temp.name)
        example = self.repo / "examples" / "patterns" / "demo"
        example.mkdir(parents=True)
        (example / "main.py").write_text("print('demo')\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        conformance = self.repo / "conformance"
        conformance.mkdir()
        self.manifest_path = conformance / "examples_manifest.json"
        self.ledger_path = conformance / "examples_publication_ledger.json"
        self.selection_path = conformance / "examples_publication_selection.json"
        self.manifest = {
            "version": "5.1.0",
            "examples": [
                {
                    "name": "demo",
                    "description": "Migration fixture",
                    "category": "patterns",
                    "required": True,
                    "scenario": "Migrate identity",
                    "real_world_application": "Publication testing",
                    "tech_tags": ["LLM"],
                    "languages": ["python"],
                    "implementations": {"python": "examples/patterns/demo/main.py"},
                    "tier": "community",
                    "content_hash": "a" * 64,
                }
            ],
        }
        self.ledger = {
            "schema_version": "1.0.0",
            "ledger_type": "test-publication-ledger",
            "policy": {"preserve": "yes"},
            "public_channels": ["repo", "docs", "celerat", "website"],
            "entries": [
                {
                    "example_id": "demo",
                    "publication_status": "approved",
                    "public_channels": ["repo", "docs", "celerat", "website"],
                    "approved_release": "test-release",
                    "approved_content_hash": "a" * 64,
                    "approved_source_ref": {
                        "kind": "current_source",
                        "ref": "conformance/examples_manifest.json",
                        "public_safe": True,
                    },
                    "public_clearance": {
                        "state": "approved_public",
                        "authority": "leadership_team",
                        "scope": ["repo", "docs", "celerat", "website"],
                        "profile": "production_ready",
                    },
                    "current_content_hash": "a" * 64,
                    "current_changes_public_ready": True,
                    "notes": "preserve exactly",
                }
            ],
        }
        self.write_json(self.manifest_path, self.manifest)
        self.write_json(self.ledger_path, self.ledger)
        self.write_json(self.selection_path, {"legacy": True})
        self.git("init", "-q")
        self.git("config", "user.name", "Migration Test")
        self.git("config", "user.email", "migration@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.commit_sha = self.git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def migrate(self, source_ref: str | None = None) -> None:
        self.generator.migrate_tree_digest_files(
            self.manifest_path,
            self.ledger_path,
            self.selection_path,
            repo=self.repo,
            source_ref=source_ref or self.commit_sha,
        )

    def recommit_metadata(self) -> None:
        self.write_json(self.manifest_path, self.manifest)
        self.write_json(self.ledger_path, self.ledger)
        self.git("add", "conformance")
        self.git("commit", "-qm", "change metadata fixture")
        self.commit_sha = self.git("rev-parse", "HEAD").stdout.strip()

    def test_requires_full_commit_and_clean_tracked_source(self) -> None:
        with self.assertRaisesRegex(
            self.generator.PublicationError, "full 40-character"
        ):
            self.migrate(self.commit_sha[:12])

        (self.repo / "examples" / "patterns" / "demo" / "main.py").write_text(
            "print('dirty')\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            self.generator.PublicationError, "tracked migration inputs are dirty"
        ):
            self.migrate()

    def test_refuses_nonignored_untracked_public_input(self) -> None:
        (self.repo / "examples" / "patterns" / "demo" / "UNTRACKED.md").write_text(
            "blocked\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(
            self.generator.PublicationError, "non-ignored untracked"
        ):
            self.migrate()

    def test_refuses_unapproved_or_ambiguous_current_source(self) -> None:
        self.ledger["entries"][0]["approved_content_hash"] = "b" * 64
        self.recommit_metadata()

        with self.assertRaisesRegex(
            self.generator.PublicationError, "pre-existing content approval"
        ):
            self.migrate()

    def test_refuses_local_tree_without_independent_digest(self) -> None:
        self.ledger["entries"][0]["approved_source_ref"] = {
            "kind": "local_tree",
            "public_safe": True,
            "example_dir": "approved/demo",
        }
        self.recommit_metadata()

        with self.assertRaisesRegex(
            self.generator.PublicationError,
            "local_tree.*approved_source_tree_sha256",
        ):
            self.migrate()

    def test_migration_is_bounded_and_byte_idempotent(self) -> None:
        before_manifest = json.loads(self.manifest_path.read_text())
        before_ledger = json.loads(self.ledger_path.read_text())

        self.migrate()

        migrated_manifest = json.loads(self.manifest_path.read_text())
        migrated_ledger = json.loads(self.ledger_path.read_text())
        migrated_selection = json.loads(self.selection_path.read_text())
        digest = digest_git_tree(self.repo, "examples/patterns/demo", self.commit_sha)
        self.assertEqual(migrated_manifest["version"], "5.2.0")
        self.assertEqual(migrated_manifest["examples"][0]["source_tree_sha256"], digest)
        entry = migrated_ledger["entries"][0]
        self.assertEqual(migrated_ledger["schema_version"], "1.1.0")
        self.assertEqual(entry["approved_source_tree_sha256"], digest)
        self.assertEqual(entry["current_source_tree_sha256"], digest)
        self.assertEqual(
            migrated_selection["publication_selection"]["schema_version"],
            "1.1.0",
        )
        self.assertEqual(
            migrated_selection["publication_selection"]["approved_examples"][0][
                "selected_source"
            ]["source_tree_sha256"],
            digest,
        )
        self.assertEqual(
            migrated_manifest["examples"][0]["content_hash"],
            before_manifest["examples"][0]["content_hash"],
        )
        protected = {
            "approved_content_hash",
            "current_content_hash",
            "approved_release",
            "publication_status",
            "public_channels",
            "public_clearance",
            "current_changes_public_ready",
            "approved_source_ref",
            "notes",
        }
        self.assertEqual(
            {key: before_ledger["entries"][0][key] for key in protected},
            {key: entry[key] for key in protected},
        )

        first = tuple(
            path.read_bytes()
            for path in (self.manifest_path, self.ledger_path, self.selection_path)
        )
        self.migrate()
        second = tuple(
            path.read_bytes()
            for path in (self.manifest_path, self.ledger_path, self.selection_path)
        )
        self.assertEqual(first, second)


class WorkflowContractTests(unittest.TestCase):
    SAFE_COMMANDS = (
        "set -euo pipefail",
        "EXPORT=/tmp/nxusKit-examples-export",
        'rm -rf "$EXPORT"',
        'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA"',
        'python3 scripts/examples_publication_tree.py materialize-public-export --repo . --source-ref "$GITHUB_SHA" --output "$EXPORT"',
        'python3 scripts/generate-examples-publication-selection.py --check --source-ref "$GITHUB_SHA" --filter-export "$EXPORT"',
        'python3 scripts/examples_publication_tree.py attest-public-export --export-root "$EXPORT"',
    )

    @classmethod
    def workflow(cls, commands: tuple[str, ...] | None = None) -> str:
        body = "\n".join(
            f"          {line}" for line in (commands or cls.SAFE_COMMANDS)
        )
        return f"""name: Safe publication fixture
jobs:
  mirror:
    steps:
      - name: Harmless preparation
        run: |
          set -euo pipefail
          echo prepare
      - name: Export approved tracked content
        run: |
{body}
      - name: Post-attestation read
        run: |
          set -euo pipefail
          echo complete
"""

    def setUp(self) -> None:
        self.checker = load_publication_workflow_checker()

    def errors(self, text: str) -> list[str]:
        return self.checker.validate_private_workflow(text)

    def test_safe_contract_passes(self) -> None:
        self.assertEqual(self.errors(self.workflow()), [])

    def test_each_required_command_is_mandatory_and_exact_sha_bound(self) -> None:
        for command in self.SAFE_COMMANDS[2:]:
            with self.subTest(command=command):
                commands = tuple(item for item in self.SAFE_COMMANDS if item != command)
                self.assertTrue(self.errors(self.workflow(commands)))
        unsafe = self.workflow().replace(
            '--source-ref "$GITHUB_SHA"', '--source-ref "$OTHER_SHA"', 1
        )
        self.assertTrue(self.errors(unsafe))

    def test_order_duplicates_and_extra_export_writes_are_rejected(self) -> None:
        swapped = list(self.SAFE_COMMANDS)
        swapped[-1], swapped[-2] = swapped[-2], swapped[-1]
        self.assertTrue(self.errors(self.workflow(tuple(swapped))))
        for command in self.SAFE_COMMANDS[3:]:
            with self.subTest(duplicate=command):
                duplicated = (*self.SAFE_COMMANDS, command)
                self.assertTrue(self.errors(self.workflow(duplicated)))
        duplicate_step = self.workflow().replace(
            "      - name: Post-attestation read",
            "      - name: Export approved tracked content\n"
            "        run: |\n"
            "          set -euo pipefail\n"
            "          echo duplicate\n"
            "      - name: Post-attestation read",
        )
        self.assertTrue(self.errors(duplicate_step))
        prewrite = self.workflow().replace(
            "          echo prepare",
            '          echo unsafe > "$EXPORT"',
        )
        self.assertTrue(self.errors(prewrite))

    def test_ambient_copy_mechanisms_are_rejected(self) -> None:
        for unsafe in (
            'cp -a examples "$EXPORT"',
            'cp -R examples "$EXPORT"',
            'rsync -a examples/ "$EXPORT"',
            'python3 -c \'import shutil; shutil.copytree("examples", "out")\'',
            'tar cf - examples | tar xf - -C "$EXPORT"',
            'git archive HEAD > "$EXPORT/tree.tar"',
        ):
            with self.subTest(unsafe=unsafe):
                commands = (*self.SAFE_COMMANDS[:-1], unsafe, self.SAFE_COMMANDS[-1])
                self.assertTrue(self.errors(self.workflow(commands)))

    def test_live_layout_matches_contract(self) -> None:
        private_workflow = REPO / ".github" / "workflows" / "publish-to-public.yml"
        if private_workflow.is_file():
            self.assertEqual(self.errors(private_workflow.read_text()), [])
        else:
            self.assertEqual(self.checker.validate_layout(REPO, "public"), [])


class IntegrationWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = load_publication_workflow_checker()
        self.layout = (
            "private"
            if (REPO / ".github/workflows/publish-to-public.yml").is_file()
            else "public"
        )
        self.documents = self.checker.integration_documents(REPO, self.layout)

    def test_all_private_public_and_exported_gates_are_wired(self) -> None:
        self.assertEqual(
            self.checker.validate_integration_documents(self.documents, self.layout), []
        )

    def test_removing_each_required_command_fails_closed(self) -> None:
        requirements = self.checker.wiring_requirements(self.layout)
        for label, commands in requirements.items():
            for command in commands:
                with self.subTest(label=label, command=command):
                    mutated = dict(self.documents)
                    mutated[label] = mutated[label].replace(command, "", 1)
                    errors = self.checker.validate_integration_documents(
                        mutated, self.layout
                    )
                    self.assertTrue(
                        any(label in error and command in error for error in errors),
                        errors,
                    )

    def test_public_layout_accepts_only_exported_public_ci_wiring(self) -> None:
        public_ci_source = REPO / ".github" / "workflows-public" / "ci.yml"
        public_ci = (
            public_ci_source.read_text(encoding="utf-8")
            if public_ci_source.is_file()
            else self.documents["public_ci"]
        )
        documents = {"public_ci": public_ci}

        self.assertEqual(
            self.checker.validate_integration_documents(documents, "public"), []
        )
        for command in self.checker.wiring_requirements("public")["public_ci"]:
            with self.subTest(command=command):
                mutated = {"public_ci": public_ci.replace(command, "", 1)}
                errors = self.checker.validate_integration_documents(mutated, "public")
                self.assertTrue(
                    any("public_ci" in error and command in error for error in errors),
                    errors,
                )

    def test_private_layout_rejects_public_only_document_set(self) -> None:
        public_only = {"public_ci": self.documents["public_ci"]}

        errors = self.checker.validate_integration_documents(public_only, "private")

        self.assertTrue(any("pre_pr" in error for error in errors), errors)
        self.assertTrue(any("private_ci" in error for error in errors), errors)
        self.assertTrue(any("mirror" in error for error in errors), errors)


class GeneratorLayoutIdentityTests(unittest.TestCase):
    def test_public_layout_uses_attested_filesystem_tree_without_git(self) -> None:
        generator = load_publication_generator()
        with tempfile.TemporaryDirectory(prefix="public-generator-layout-") as tmp:
            repo = Path(tmp)
            example = repo / "examples" / "patterns" / "demo"
            example.mkdir(parents=True)
            (example / "main.py").write_text("print('demo')\n", encoding="utf-8")
            expected = source_tree_sha256(filesystem_tree_entries(example))

            with mock.patch.object(
                generator,
                "git_tree_entries",
                side_effect=AssertionError("public layout must not invoke Git"),
            ):
                entries = generator.repository_tree_entries(
                    repo, "examples/patterns/demo", None
                )
                actual = generator.repository_tree_sha256(
                    repo, "examples/patterns/demo", None
                )

        self.assertEqual(source_tree_sha256(entries), expected)
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
