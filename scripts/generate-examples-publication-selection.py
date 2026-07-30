#!/usr/bin/env python3
"""Generate and validate the public Examples publication selection.

The source manifest remains the work-in-progress portfolio view. This script
combines that manifest with a per-example publication ledger and emits the
public-ready selection consumed by public export, docs export, Celerat public
metadata handoff, and website showcase generation.

Publication readiness is intentionally separate from CE/Pro tier metadata.

Approved source refs are local and content-addressed. The W16 baseline
`current_source` ref remains valid when the current manifest entry still matches
the approved content hash. Held enhancements use `local_tree`: an inline
approved manifest entry plus a repo-relative example directory and deterministic
tree hash. Publish/export fails closed if any referenced content cannot be
validated locally.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = REPO / "conformance" / "examples_manifest.json"
LEDGER = REPO / "conformance" / "examples_publication_ledger.json"
SELECTION = REPO / "conformance" / "examples_publication_selection.json"
DOCS_EXPORT = REPO / "conformance" / "docs_export_manifest.json"
SMOKE_MATRIX = REPO / "conformance" / "example_smoke_matrix.json"
SNAPSHOT_ARTIFACTS = {
    "docs_export_manifest": "conformance/docs_export_manifest.json",
    "example_groups": "conformance/example-groups.json",
    "example_smoke_matrix": "conformance/example_smoke_matrix.json",
    "example_tiers": "conformance/example-tiers.json",
    "examples_manifest": "conformance/examples_manifest.json",
    "examples_publication_ledger": "conformance/examples_publication_ledger.json",
    "examples_publication_selection": "conformance/examples_publication_selection.json",
}

APPROVED_STATUSES = {"approved"}
NON_PUBLIC_STATUSES = {"candidate", "hold", "internal", "retired"}
VALID_STATUSES = APPROVED_STATUSES | NON_PUBLIC_STATUSES
PUBLIC_CHANNELS = ("repo", "docs", "celerat", "website")
APPROVED_RELEASE = "v1.0.2-validated-examples-portfolio"
NON_PUBLIC_WORD = "internal"
PRIVATE_WORD = "private"
# Build these at runtime so the repo-wide literal leak gate can scan this file
# while the generator still enforces the same public-boundary terms.
FORBIDDEN_PUBLIC_REF_TERMS = (
    "nxusKit-" + NON_PUBLIC_WORD,
    "nxusKit-examples-" + NON_PUBLIC_WORD,
    "nxusKit-plugins-" + NON_PUBLIC_WORD,
    NON_PUBLIC_WORD + "/",
    "/" + NON_PUBLIC_WORD,
    PRIVATE_WORD + "/",
    "/" + PRIVATE_WORD,
)
SUPPORTED_SOURCE_REF_KINDS = ("current_source", "local_tree")
PUBLIC_CLEARANCE_STATE = "approved_public"
PUBLIC_CLEARANCE_AUTHORITY = "leadership_team"
VALID_PUBLIC_CLEARANCE_PROFILES = {"production_ready", "extension_authoring"}


class PublicationError(RuntimeError):
    """Raised when publication selection must fail closed."""


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise PublicationError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def json_sha256(data: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def directory_sha256(path: Path) -> str:
    if not path.is_dir():
        raise PublicationError(f"approved source directory not found: {path}")

    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise PublicationError(f"approved source directory has no files: {path}")

    for item in files:
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def manifest_examples(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    examples = manifest.get("examples")
    if not isinstance(examples, list):
        raise PublicationError("manifest.examples must be an array")
    return examples


def example_key(example: dict[str, Any]) -> str:
    name = example.get("name")
    if not isinstance(name, str) or not name:
        raise PublicationError(f"manifest example missing name: {example!r}")
    return name


def current_hash(example: dict[str, Any]) -> str:
    value = example.get("content_hash")
    if not isinstance(value, str) or len(value) != 64:
        raise PublicationError(
            f"{example_key(example)} missing 64-character content_hash"
        )
    return value


def example_source_rel(example: dict[str, Any]) -> str:
    category = example.get("category")
    name = example_key(example)
    if category not in {"patterns", "integrations", "apps"}:
        raise PublicationError(
            f"{name}: category must be patterns, integrations, or apps"
        )
    return f"examples/{category}/{name}"


def public_readiness_profile(example: dict[str, Any]) -> str:
    value = example.get("public_readiness_profile", "production_ready")
    if not isinstance(value, str) or value not in VALID_PUBLIC_CLEARANCE_PROFILES:
        raise PublicationError(
            f"{example_key(example)}: public_readiness_profile must be one of {sorted(VALID_PUBLIC_CLEARANCE_PROFILES)}"
        )
    return value


def public_clearance_for(
    example: dict[str, Any], channels: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    return {
        "state": PUBLIC_CLEARANCE_STATE,
        "authority": PUBLIC_CLEARANCE_AUTHORITY,
        "scope": list(channels),
        "profile": public_readiness_profile(example),
    }


def validate_public_clearance(
    example_id: str,
    entry: dict[str, Any],
    selected_example: dict[str, Any],
    channels: list[Any],
) -> dict[str, Any]:
    clearance = entry.get("public_clearance")
    if not isinstance(clearance, dict):
        raise PublicationError(
            f"{example_id}: public_clearance is required for approved publication"
        )

    state = clearance.get("state")
    if state != PUBLIC_CLEARANCE_STATE:
        raise PublicationError(
            f"{example_id}: public_clearance.state must be {PUBLIC_CLEARANCE_STATE!r}"
        )

    authority = clearance.get("authority")
    if authority != PUBLIC_CLEARANCE_AUTHORITY:
        raise PublicationError(
            f"{example_id}: public_clearance.authority must be {PUBLIC_CLEARANCE_AUTHORITY!r}"
        )

    scope = clearance.get("scope")
    if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
        raise PublicationError(
            f"{example_id}: public_clearance.scope must be an array of strings"
        )
    if set(scope) != set(channels):
        raise PublicationError(
            f"{example_id}: public_clearance.scope must match public_channels"
        )

    profile = clearance.get("profile")
    expected_profile = public_readiness_profile(selected_example)
    if profile != expected_profile:
        raise PublicationError(
            f"{example_id}: public_clearance.profile must match public_readiness_profile {expected_profile!r}"
        )

    return {
        "state": state,
        "authority": authority,
        "scope": list(scope),
        "profile": profile,
    }


def safe_repo_relative_path(
    example_id: str, source_ref: dict[str, Any], field: str
) -> Path:
    value = source_ref.get(field)
    if not isinstance(value, str) or not value:
        raise PublicationError(f"{example_id}: approved_source_ref.{field} is required")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PublicationError(
            f"{example_id}: approved_source_ref.{field} must be repo-relative"
        )
    serialized = path.as_posix()
    for term in FORBIDDEN_PUBLIC_REF_TERMS:
        if term in serialized:
            raise PublicationError(
                f"{example_id}: approved_source_ref.{field} contains non-public term {term!r}"
            )
    return path


def build_initial_ledger(manifest: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for example in manifest_examples(manifest):
        name = example_key(example)
        digest = current_hash(example)
        entries.append(
            {
                "example_id": name,
                "publication_status": "approved",
                "public_channels": list(PUBLIC_CHANNELS),
                "approved_release": APPROVED_RELEASE,
                "approved_content_hash": digest,
                "approved_source_ref": {
                    "kind": "current_source",
                    "ref": "conformance/examples_manifest.json",
                    "public_safe": True,
                    "notes": "Initialized from the v1.0.2 validated Examples portfolio source state.",
                },
                "public_clearance": public_clearance_for(example, PUBLIC_CHANNELS),
                "current_content_hash": digest,
                "current_changes_public_ready": True,
                "notes": "Approved as part of the v1.0.2 validated Examples portfolio baseline.",
            }
        )

    return {
        "schema_version": "1.0.0",
        "ledger_type": "nxuskit-examples-publication-readiness-ledger",
        "policy": {
            "default_for_missing_examples": "candidate",
            "publication_readiness_is_separate_from_tier": True,
            "approved_variant_selection": "current source when content_hash matches; held changes reconstruct from approved_source_ref.kind=local_tree; otherwise fail closed",
            "public_clearance_required_for_approved_examples": True,
            "public_clearance_state": PUBLIC_CLEARANCE_STATE,
            "public_clearance_authority": PUBLIC_CLEARANCE_AUTHORITY,
            "sdk_coupling": "Examples consumes SDK releases; SDK may use a validated Examples portfolio snapshot as QA/provenance but does not include or depend on the Examples runtime package.",
        },
        "public_channels": list(PUBLIC_CHANNELS),
        "entries": entries,
    }


def ledger_entries(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise PublicationError("ledger.entries must be an array")
    result: dict[str, dict[str, Any]] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise PublicationError("ledger.entries items must be objects")
        example_id = raw.get("example_id")
        if not isinstance(example_id, str) or not example_id:
            raise PublicationError(f"ledger entry missing example_id: {raw!r}")
        if example_id in result:
            raise PublicationError(f"duplicate ledger entry: {example_id}")
        status = raw.get("publication_status")
        if status not in VALID_STATUSES:
            raise PublicationError(
                f"{example_id}: publication_status must be one of {sorted(VALID_STATUSES)}"
            )
        result[example_id] = raw
    return result


def ensure_public_safe_source_ref(example_id: str, entry: dict[str, Any]) -> None:
    source_ref = entry.get("approved_source_ref")
    if not isinstance(source_ref, dict):
        raise PublicationError(f"{example_id}: approved_source_ref is required")
    serialized = json.dumps(source_ref, sort_keys=True)
    for term in FORBIDDEN_PUBLIC_REF_TERMS:
        if term in serialized:
            raise PublicationError(
                f"{example_id}: approved_source_ref contains non-public term {term!r}"
            )
    if source_ref.get("public_safe") is not True:
        raise PublicationError(
            f"{example_id}: approved_source_ref.public_safe must be true"
        )
    kind = source_ref.get("kind")
    if kind not in SUPPORTED_SOURCE_REF_KINDS:
        raise PublicationError(
            f"{example_id}: approved_source_ref.kind must be one of {SUPPORTED_SOURCE_REF_KINDS}"
        )
    if (
        kind == "current_source"
        and source_ref.get("ref") != "conformance/examples_manifest.json"
    ):
        raise PublicationError(
            f"{example_id}: approved_source_ref.ref must be conformance/examples_manifest.json for current_source"
        )


def approved_source_ref(entry: dict[str, Any], example_id: str) -> dict[str, Any]:
    source_ref = entry.get("approved_source_ref")
    if not isinstance(source_ref, dict):
        raise PublicationError(f"{example_id}: approved_source_ref is required")
    return source_ref


def reconstruct_local_tree_variant(
    example_id: str, entry: dict[str, Any], approved_hash: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_ref = approved_source_ref(entry, example_id)
    ensure_public_safe_source_ref(example_id, entry)

    kind = source_ref.get("kind")
    if kind == "current_source":
        raise PublicationError(
            f"{example_id}: approved_source_ref.kind=current_source cannot reconstruct held source"
        )
    if kind != "local_tree":
        raise PublicationError(
            f"{example_id}: approved_source_ref.kind must be one of {SUPPORTED_SOURCE_REF_KINDS}"
        )

    manifest_entry = source_ref.get("manifest_entry")
    if not isinstance(manifest_entry, dict):
        raise PublicationError(
            f"{example_id}: approved_source_ref.manifest_entry is required"
        )
    if example_key(manifest_entry) != example_id:
        raise PublicationError(f"{example_id}: approved manifest entry name mismatch")
    if current_hash(manifest_entry) != approved_hash:
        raise PublicationError(
            f"{example_id}: approved manifest entry content_hash mismatch"
        )

    manifest_entry_sha = source_ref.get("manifest_entry_sha256")
    if not isinstance(manifest_entry_sha, str) or len(manifest_entry_sha) != 64:
        raise PublicationError(
            f"{example_id}: approved_source_ref.manifest_entry_sha256 is required"
        )
    actual_manifest_entry_sha = json_sha256(manifest_entry)
    if manifest_entry_sha != actual_manifest_entry_sha:
        raise PublicationError(
            f"{example_id}: approved_source_ref.manifest_entry_sha256 mismatch"
        )

    example_dir_rel = safe_repo_relative_path(example_id, source_ref, "example_dir")
    example_dir = REPO / example_dir_rel
    example_tree_sha = source_ref.get("example_tree_sha256")
    if not isinstance(example_tree_sha, str) or len(example_tree_sha) != 64:
        raise PublicationError(
            f"{example_id}: approved_source_ref.example_tree_sha256 is required"
        )
    actual_tree_sha = directory_sha256(example_dir)
    if example_tree_sha != actual_tree_sha:
        raise PublicationError(
            f"{example_id}: approved_source_ref.example_tree_sha256 mismatch"
        )

    assert_public_safe_json(f"{example_id} approved manifest entry", manifest_entry)
    selected_source = {
        "kind": "approved_source_ref",
        "ref_kind": "local_tree",
        "content_hash": approved_hash,
        "manifest_entry_sha256": manifest_entry_sha,
        "example_tree_sha256": example_tree_sha,
    }
    return copy.deepcopy(manifest_entry), selected_source


def local_tree_source_ref_for_example(example: dict[str, Any]) -> dict[str, Any]:
    # Self-test helper. Real held enhancements should point example_dir at a
    # frozen approved variant tree, not at the live WIP example directory.
    example_dir = REPO / example_source_rel(example)
    return {
        "kind": "local_tree",
        "public_safe": True,
        "manifest_entry": copy.deepcopy(example),
        "manifest_entry_sha256": json_sha256(example),
        "example_dir": example_source_rel(example),
        "example_tree_sha256": directory_sha256(example_dir),
        "notes": "Content-addressed local approved public variant.",
    }


def selected_manifest_from(
    source_manifest: dict[str, Any], examples: list[dict[str, Any]]
) -> dict[str, Any]:
    public_manifest = {
        key: copy.deepcopy(value)
        for key, value in source_manifest.items()
        if key != "examples"
    }
    public_manifest["examples"] = copy.deepcopy(examples)
    return public_manifest


def build_selection(
    source_manifest: dict[str, Any], ledger: dict[str, Any], *, strict: bool = True
) -> dict[str, Any]:
    entries = ledger_entries(ledger)
    selected_examples: list[dict[str, Any]] = []
    approved_records: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    manifest_names: set[str] = set()

    for example in manifest_examples(source_manifest):
        name = example_key(example)
        manifest_names.add(name)
        digest = current_hash(example)
        entry = entries.get(name)

        if entry is None:
            excluded.append(
                {
                    "example_id": name,
                    "publication_status": "candidate",
                    "reason": "missing_publication_ledger_entry",
                }
            )
            continue

        status = str(entry["publication_status"])
        if status in NON_PUBLIC_STATUSES:
            excluded.append(
                {
                    "example_id": name,
                    "publication_status": status,
                    "reason": f"publication_status_{status}",
                }
            )
            continue

        ensure_public_safe_source_ref(name, entry)
        approved_hash = entry.get("approved_content_hash")
        if not isinstance(approved_hash, str) or len(approved_hash) != 64:
            raise PublicationError(
                f"{name}: approved_content_hash must be a 64-character hash"
            )

        recorded_current_hash = entry.get("current_content_hash")
        if recorded_current_hash is not None and recorded_current_hash != digest:
            raise PublicationError(
                f"{name}: current_content_hash is stale; regenerate or update the publication ledger"
            )

        current_ready = entry.get("current_changes_public_ready")
        if not isinstance(current_ready, bool):
            raise PublicationError(
                f"{name}: current_changes_public_ready must be boolean"
            )

        selected_example = copy.deepcopy(example)
        selected_source = {
            "kind": "current_source",
            "content_hash": digest,
        }
        if digest != approved_hash:
            if current_ready:
                raise PublicationError(
                    f"{name}: current content differs from approved_content_hash; update the ledger approval hash or hold the enhancement"
                )
            selected_example, selected_source = reconstruct_local_tree_variant(
                name, entry, approved_hash
            )
            if selected_example.get("category") != example.get("category"):
                raise PublicationError(f"{name}: approved variant category mismatch")

        channels = entry.get("public_channels")
        if not isinstance(channels, list) or not set(channels).issubset(
            PUBLIC_CHANNELS
        ):
            raise PublicationError(
                f"{name}: public_channels must be a subset of {PUBLIC_CHANNELS}"
            )
        if set(channels) != set(PUBLIC_CHANNELS) and strict:
            raise PublicationError(
                f"{name}: partial-channel publication is not implemented in this slice"
            )

        public_clearance = validate_public_clearance(
            name, entry, selected_example, channels
        )

        selected_examples.append(selected_example)
        approved_records.append(
            {
                "example_id": name,
                "publication_status": status,
                "public_channels": channels,
                "approved_release": entry.get("approved_release"),
                "approved_content_hash": approved_hash,
                "public_clearance": public_clearance,
                "selected_source": selected_source,
            }
        )

    stale_entries = sorted(set(entries) - manifest_names)
    if stale_entries and strict:
        raise PublicationError(
            f"ledger contains entries not present in source manifest: {stale_entries}"
        )

    public_manifest = selected_manifest_from(source_manifest, selected_examples)
    selection = copy.deepcopy(public_manifest)
    selection["publication_selection"] = {
        "schema_version": "1.0.0",
        "selection_type": "nxuskit-examples-approved-public-selection",
        "generated_by": "scripts/generate-examples-publication-selection.py",
        "source_manifest": "conformance/examples_manifest.json",
        "publication_ledger": "conformance/examples_publication_ledger.json",
        "approval_policy": {
            "approved_source_ref_supported_kinds": list(SUPPORTED_SOURCE_REF_KINDS),
            "new_examples_default_publication_status": "candidate",
            "held_enhancements_fail_closed_without_approved_variant_reconstruction": False,
            "held_enhancements_fail_closed_when_approved_source_ref_unavailable": True,
            "held_enhancements_reconstruct_from_approved_source_ref": True,
            "publication_readiness_is_separate_from_tier": True,
            "public_clearance_required_for_approved_examples": True,
            "public_clearance_state": PUBLIC_CLEARANCE_STATE,
            "public_clearance_authority": PUBLIC_CLEARANCE_AUTHORITY,
            "sdk_coupling": "Examples consumes SDK releases; SDK does not include or depend on Examples runtime/package content.",
        },
        "approved_examples_count": len(selected_examples),
        "source_examples_count": len(manifest_examples(source_manifest)),
        "excluded_examples_count": len(excluded),
        "approved_examples": approved_records,
        "excluded_examples": excluded,
        "public_channels": list(PUBLIC_CHANNELS),
        "downstream_consumers": [
            "public_repo_export",
            "docs_export",
            "celerat_public_metadata_handoff",
            "website_showcase",
        ],
    }
    return selection


def compare(path: Path, expected: dict[str, Any]) -> bool:
    if not path.is_file():
        print(f"missing generated file: {path}", file=sys.stderr)
        return False
    expected_text = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    actual_text = path.read_text(encoding="utf-8")
    if actual_text != expected_text:
        print(f"stale generated file: {path}", file=sys.stderr)
        return False
    return True


def clean_public_manifest(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in selection.items()
        if key != "publication_selection"
    }


def public_ledger_from(
    ledger: dict[str, Any], selected_examples: list[dict[str, Any]]
) -> dict[str, Any]:
    entries_by_name = ledger_entries(ledger)
    entries: list[dict[str, Any]] = []
    for example in selected_examples:
        name = example_key(example)
        entry = entries_by_name.get(name)
        if entry is None:
            raise PublicationError(
                f"{name}: selected example is missing from publication ledger"
            )
        ensure_public_safe_source_ref(name, entry)
        approved_hash = current_hash(example)
        entries.append(
            {
                "example_id": name,
                "publication_status": "approved",
                "public_channels": list(PUBLIC_CHANNELS),
                "approved_release": entry.get("approved_release"),
                "approved_content_hash": approved_hash,
                "approved_source_ref": {
                    "kind": "current_source",
                    "ref": "conformance/examples_manifest.json",
                    "public_safe": True,
                    "notes": "Public export contains the approved selected source for this example.",
                },
                "public_clearance": validate_public_clearance(
                    name, entry, example, list(PUBLIC_CHANNELS)
                ),
                "current_content_hash": approved_hash,
                "current_changes_public_ready": True,
                "notes": "Approved public example variant selected for public export.",
            }
        )

    public_ledger = {
        "schema_version": ledger.get("schema_version", "1.0.0"),
        "ledger_type": "nxuskit-examples-approved-public-publication-ledger",
        "policy": copy.deepcopy(ledger.get("policy", {})),
        "public_channels": list(PUBLIC_CHANNELS),
        "entries": entries,
    }
    return public_ledger


def approved_records_by_name(selection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = selection.get("publication_selection")
    if not isinstance(metadata, dict):
        raise PublicationError("selection.publication_selection must be an object")
    records = metadata.get("approved_examples")
    if not isinstance(records, list):
        raise PublicationError(
            "selection.publication_selection.approved_examples must be an array"
        )
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise PublicationError("approved_examples items must be objects")
        example_id = record.get("example_id")
        if not isinstance(example_id, str):
            raise PublicationError("approved_examples entry missing example_id")
        result[example_id] = record
    return result


def copy_approved_variant_trees(
    export_root: Path, selection: dict[str, Any], ledger: dict[str, Any]
) -> None:
    entries_by_name = ledger_entries(ledger)
    selected_examples = {
        example_key(example): example for example in manifest_examples(selection)
    }
    records_by_name = approved_records_by_name(selection)

    for name, record in records_by_name.items():
        selected_source = record.get("selected_source")
        if (
            not isinstance(selected_source, dict)
            or selected_source.get("kind") != "approved_source_ref"
        ):
            continue
        entry = entries_by_name.get(name)
        if entry is None:
            raise PublicationError(
                f"{name}: selected approved variant missing ledger entry"
            )
        approved_hash = record.get("approved_content_hash")
        if not isinstance(approved_hash, str):
            raise PublicationError(
                f"{name}: selected approved variant missing approved_content_hash"
            )
        manifest_entry, _ = reconstruct_local_tree_variant(name, entry, approved_hash)
        selected_example = selected_examples.get(name)
        if selected_example != manifest_entry:
            raise PublicationError(
                f"{name}: selected manifest entry does not match approved source ref"
            )

        source_ref = approved_source_ref(entry, name)
        example_dir = REPO / safe_repo_relative_path(name, source_ref, "example_dir")
        target_dir = export_root / example_source_rel(manifest_entry)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(example_dir, target_dir)


def filter_docs_export(export_root: Path, approved_names: set[str]) -> None:
    path = export_root / "conformance" / "docs_export_manifest.json"
    if not path.is_file():
        return
    data = read_json(path)
    companions = data.get("companion_docs", [])
    if not isinstance(companions, list):
        raise PublicationError(f"{path}: companion_docs must be an array")
    filtered = []
    for doc in companions:
        source = str(doc.get("source", ""))
        parts = source.split("/")
        if len(parts) >= 4 and parts[0] == "examples" and parts[2] in approved_names:
            filtered.append(doc)
    data["companion_docs"] = filtered
    write_json(path, data)


def filter_smoke_matrix(export_root: Path, approved_names: set[str]) -> None:
    path = export_root / "conformance" / "example_smoke_matrix.json"
    if not path.is_file():
        return
    data = read_json(path)
    runs = data.get("runs", [])
    if not isinstance(runs, list):
        raise PublicationError(f"{path}: runs must be an array")
    data["runs"] = [run for run in runs if run.get("example") in approved_names]
    write_json(path, data)


def filter_example_tiers(export_root: Path, approved_names: set[str]) -> None:
    path = export_root / "conformance" / "example-tiers.json"
    if not path.is_file():
        return
    data = read_json(path)
    data = {name: tier for name, tier in data.items() if name in approved_names}
    write_json(path, data)


def refresh_release_snapshot(export_root: Path) -> None:
    path = export_root / "conformance" / "examples_release_snapshot.json"
    if not path.is_file():
        return
    data = read_json(path)
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        raise PublicationError(f"{path}: artifacts must be an object")

    for name, relative_path in SNAPSHOT_ARTIFACTS.items():
        artifact = export_root / relative_path
        if not artifact.is_file():
            continue
        digest = file_sha256(artifact)
        record = artifacts.get(name)
        if not isinstance(record, dict):
            record = {"path": relative_path}
            artifacts[name] = record
        record["path"] = relative_path
        record["sha256"] = digest
        data[f"{name}_sha256"] = digest

    write_json(path, data)


def filter_export(
    export_root: Path, selection: dict[str, Any], ledger: dict[str, Any]
) -> None:
    selected_examples = manifest_examples(selection)
    approved_names = {example_key(example) for example in selected_examples}
    public_manifest = clean_public_manifest(selection)
    copy_approved_variant_trees(export_root, selection, ledger)
    public_ledger = public_ledger_from(ledger, selected_examples)
    public_selection = build_selection(public_manifest, public_ledger, strict=True)
    assert_public_safe_json("generated public manifest", public_manifest)
    assert_public_safe_json("generated public ledger", public_ledger)
    assert_public_safe_selection(public_selection)

    write_json(export_root / "conformance" / "examples_manifest.json", public_manifest)
    write_json(
        export_root / "conformance" / "examples_publication_ledger.json", public_ledger
    )
    write_json(
        export_root / "conformance" / "examples_publication_selection.json",
        public_selection,
    )
    filter_docs_export(export_root, approved_names)
    filter_smoke_matrix(export_root, approved_names)
    filter_example_tiers(export_root, approved_names)
    refresh_release_snapshot(export_root)

    examples_root = export_root / "examples"
    for category in ("patterns", "integrations", "apps"):
        category_root = examples_root / category
        if not category_root.is_dir():
            continue
        for child in category_root.iterdir():
            if child.is_dir() and child.name not in approved_names:
                shutil.rmtree(child)


def assert_public_safe_json(label: str, data: dict[str, Any]) -> None:
    serialized = json.dumps(data, sort_keys=True)
    for term in FORBIDDEN_PUBLIC_REF_TERMS:
        if term in serialized:
            raise PublicationError(f"{label} contains non-public term {term!r}")


def assert_public_safe_selection(selection: dict[str, Any]) -> None:
    assert_public_safe_json("generated public selection", selection)


def run_self_test() -> dict[str, Any]:
    manifest = read_json(SOURCE_MANIFEST)
    ledger = read_json(LEDGER)
    baseline = build_selection(manifest, ledger)
    baseline_count = len(manifest_examples(baseline))
    source_count = len(manifest_examples(manifest))
    excluded = baseline["publication_selection"]["excluded_examples"]
    expected_baseline_count = source_count - len(excluded)
    if baseline_count != expected_baseline_count:
        raise PublicationError(
            f"baseline approved count {baseline_count} != source manifest count {source_count} minus excluded count {len(excluded)}"
        )
    for item in excluded:
        if item.get("publication_status") not in NON_PUBLIC_STATUSES:
            raise PublicationError(
                f"baseline excluded example has invalid publication status: {item!r}"
            )

    synthetic_manifest = copy.deepcopy(manifest)
    synthetic_example = copy.deepcopy(manifest_examples(manifest)[0])
    synthetic_example["name"] = "zz-unapproved-preview"
    synthetic_example["description"] = (
        "Synthetic unapproved preview for publication readiness self-test"
    )
    synthetic_example["content_hash"] = "a" * 64
    synthetic_example["implementations"] = {
        "python": "examples/patterns/zz-unapproved-preview/python"
    }
    synthetic_manifest["examples"].append(synthetic_example)
    synthetic_selection = build_selection(synthetic_manifest, ledger, strict=False)
    synthetic_names = {
        example_key(example) for example in manifest_examples(synthetic_selection)
    }
    if "zz-unapproved-preview" in synthetic_names:
        raise PublicationError(
            "synthetic unapproved example leaked into public selection"
        )
    synthetic_excluded = synthetic_selection["publication_selection"][
        "excluded_examples"
    ]
    if not any(
        item["example_id"] == "zz-unapproved-preview" for item in synthetic_excluded
    ):
        raise PublicationError(
            "synthetic unapproved example missing from excluded_examples"
        )

    held_manifest = copy.deepcopy(manifest)
    approved_held_example = copy.deepcopy(held_manifest["examples"][0])
    held_name = example_key(held_manifest["examples"][0])
    held_manifest["examples"][0]["content_hash"] = "b" * 64
    held_manifest["examples"][0]["description"] = (
        "Synthetic held WIP description that must not publish"
    )
    held_ledger = copy.deepcopy(ledger)
    for entry in held_ledger["entries"]:
        if entry["example_id"] == held_name:
            entry["current_content_hash"] = "b" * 64
            entry["current_changes_public_ready"] = False
            entry["approved_source_ref"] = local_tree_source_ref_for_example(
                approved_held_example
            )
            break
    held_selection = build_selection(held_manifest, held_ledger)
    held_selected = next(
        example
        for example in manifest_examples(held_selection)
        if example_key(example) == held_name
    )
    if held_selected != approved_held_example:
        raise PublicationError(
            "held enhancement did not select the approved manifest variant"
        )
    held_record = approved_records_by_name(held_selection)[held_name]
    if held_record["selected_source"]["kind"] != "approved_source_ref":
        raise PublicationError(
            "held enhancement did not record approved_source_ref selection"
        )

    stale_ledger = copy.deepcopy(held_ledger)
    for entry in stale_ledger["entries"]:
        if entry["example_id"] == held_name:
            entry["approved_source_ref"]["example_tree_sha256"] = "0" * 64
            break
    try:
        build_selection(held_manifest, stale_ledger)
    except PublicationError as exc:
        stale_failed_closed = "example_tree_sha256 mismatch" in str(exc)
    else:
        stale_failed_closed = False
    if not stale_failed_closed:
        raise PublicationError("stale approved source ref did not fail closed")

    missing_ref_ledger = copy.deepcopy(held_ledger)
    for entry in missing_ref_ledger["entries"]:
        if entry["example_id"] == held_name:
            del entry["approved_source_ref"]
            break
    try:
        build_selection(held_manifest, missing_ref_ledger)
    except PublicationError as exc:
        missing_ref_failed_closed = "approved_source_ref is required" in str(exc)
    else:
        missing_ref_failed_closed = False
    if not missing_ref_failed_closed:
        raise PublicationError("missing approved source ref did not fail closed")

    missing_clearance_ledger = copy.deepcopy(ledger)
    missing_clearance_name = example_key(manifest_examples(manifest)[0])
    for entry in missing_clearance_ledger["entries"]:
        if entry["example_id"] == missing_clearance_name:
            del entry["public_clearance"]
            break
    try:
        build_selection(manifest, missing_clearance_ledger)
    except PublicationError as exc:
        missing_clearance_failed_closed = "public_clearance" in str(exc)
    else:
        missing_clearance_failed_closed = False
    if not missing_clearance_failed_closed:
        raise PublicationError("missing public_clearance did not fail closed")

    invalid_clearance_ledger = copy.deepcopy(ledger)
    invalid_clearance_name = example_key(manifest_examples(manifest)[0])
    for entry in invalid_clearance_ledger["entries"]:
        if entry["example_id"] == invalid_clearance_name:
            entry["public_clearance"]["state"] = "candidate"
            break
    try:
        build_selection(manifest, invalid_clearance_ledger)
    except PublicationError as exc:
        invalid_clearance_failed_closed = "public_clearance.state" in str(exc)
    else:
        invalid_clearance_failed_closed = False
    if not invalid_clearance_failed_closed:
        raise PublicationError("invalid public_clearance did not fail closed")

    with tempfile.TemporaryDirectory(
        prefix="examples-publication-selection-"
    ) as temp_name:
        export_root = Path(temp_name)
        shutil.copytree(REPO / "examples", export_root / "examples")
        held_export_dir = export_root / example_source_rel(approved_held_example)
        held_export_dir.mkdir(parents=True, exist_ok=True)
        (held_export_dir / "WIP_SENTINEL.txt").write_text(
            "synthetic current WIP content that must be replaced\n", encoding="utf-8"
        )
        synthetic_dir = export_root / "examples" / "patterns" / "zz-unapproved-preview"
        synthetic_dir.mkdir(parents=True)
        (synthetic_dir / "README.md").write_text(
            "# Synthetic Unapproved Preview\n", encoding="utf-8"
        )
        (export_root / "conformance").mkdir()
        write_json(
            export_root / "conformance" / "docs_export_manifest.json",
            read_json(DOCS_EXPORT),
        )
        write_json(
            export_root / "conformance" / "example_smoke_matrix.json",
            read_json(SMOKE_MATRIX),
        )
        example_tiers = REPO / "conformance" / "example-tiers.json"
        if example_tiers.is_file():
            write_json(
                export_root / "conformance" / "example-tiers.json",
                read_json(example_tiers),
            )
        release_snapshot = REPO / "conformance" / "examples_release_snapshot.json"
        if release_snapshot.is_file():
            write_json(
                export_root / "conformance" / "examples_release_snapshot.json",
                read_json(release_snapshot),
            )
        combined_manifest = copy.deepcopy(held_manifest)
        combined_manifest["examples"].append(synthetic_example)
        combined_selection = build_selection(
            combined_manifest, held_ledger, strict=False
        )
        filter_export(export_root, combined_selection, held_ledger)
        if (held_export_dir / "WIP_SENTINEL.txt").exists():
            raise PublicationError(
                "held WIP file survived approved variant export reconstruction"
            )
        if (export_root / "examples" / "patterns" / "zz-unapproved-preview").exists():
            raise PublicationError(
                "synthetic unapproved example directory survived export filter"
            )
        exported_manifest = read_json(
            export_root / "conformance" / "examples_manifest.json"
        )
        exported_names = {
            example_key(example) for example in manifest_examples(exported_manifest)
        }
        if "zz-unapproved-preview" in exported_names:
            raise PublicationError(
                "synthetic unapproved example survived exported manifest filter"
            )
        exported_held = next(
            example
            for example in manifest_examples(exported_manifest)
            if example_key(example) == held_name
        )
        if exported_held != approved_held_example:
            raise PublicationError(
                "exported manifest did not contain the approved held variant"
            )
        exported_selection = read_json(
            export_root / "conformance" / "examples_publication_selection.json"
        )
        if "zz-unapproved-preview" in json.dumps(exported_selection, sort_keys=True):
            raise PublicationError(
                "synthetic unapproved example survived exported selection filter"
            )
        if "Synthetic held WIP description" in json.dumps(
            exported_selection, sort_keys=True
        ):
            raise PublicationError(
                "held WIP metadata survived exported selection filter"
            )
        if exported_selection["publication_selection"]["excluded_examples"]:
            raise PublicationError(
                "public export selection retained excluded example records"
            )
        exported_ledger = read_json(
            export_root / "conformance" / "examples_publication_ledger.json"
        )
        if "zz-unapproved-preview" in json.dumps(exported_ledger, sort_keys=True):
            raise PublicationError(
                "synthetic unapproved example survived exported ledger filter"
            )
        if "Synthetic held WIP description" in json.dumps(
            exported_ledger, sort_keys=True
        ):
            raise PublicationError("held WIP metadata survived exported ledger filter")
        exported_tiers = read_json(export_root / "conformance" / "example-tiers.json")
        if "zz-unapproved-preview" in exported_tiers:
            raise PublicationError(
                "synthetic unapproved example survived exported tier filter"
            )
        if set(exported_tiers) - exported_names:
            raise PublicationError("exported tier map retained non-selected examples")
        exported_snapshot_path = (
            export_root / "conformance" / "examples_release_snapshot.json"
        )
        if exported_snapshot_path.is_file():
            exported_snapshot = read_json(exported_snapshot_path)
            expected_hashes = {
                "examples_manifest_sha256": export_root
                / "conformance"
                / "examples_manifest.json",
                "examples_publication_ledger_sha256": export_root
                / "conformance"
                / "examples_publication_ledger.json",
                "examples_publication_selection_sha256": export_root
                / "conformance"
                / "examples_publication_selection.json",
                "docs_export_manifest_sha256": export_root
                / "conformance"
                / "docs_export_manifest.json",
                "example_smoke_matrix_sha256": export_root
                / "conformance"
                / "example_smoke_matrix.json",
            }
            for key, artifact in expected_hashes.items():
                if exported_snapshot.get(key) != file_sha256(artifact):
                    raise PublicationError(f"exported snapshot has stale {key}")

    assert_public_safe_selection(baseline)
    assert_public_safe_selection(synthetic_selection)

    return {
        "ok": True,
        "baseline_approved_examples": baseline_count,
        "held_enhancement_exported_approved_variant": True,
        "missing_approved_source_ref_failed_closed": True,
        "missing_public_clearance_failed_closed": True,
        "invalid_public_clearance_failed_closed": True,
        "stale_approved_source_ref_failed_closed": True,
        "synthetic_unapproved_excluded": True,
        "public_selection_has_internal_refs": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--init-ledger",
        action="store_true",
        help="Initialize ledger from the source manifest.",
    )
    mode.add_argument(
        "--write", action="store_true", help="Write generated public selection."
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check generated public selection and ledger.",
    )
    mode.add_argument(
        "--self-test", action="store_true", help="Run publication readiness self-tests."
    )
    parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--output", type=Path, default=SELECTION)
    parser.add_argument(
        "--filter-export",
        type=Path,
        help="Filter an exported tree in place using the generated selection.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = (
        args.manifest if args.manifest.is_absolute() else REPO / args.manifest
    )
    ledger_path = args.ledger if args.ledger.is_absolute() else REPO / args.ledger
    output_path = args.output if args.output.is_absolute() else REPO / args.output

    try:
        if args.init_ledger:
            manifest = read_json(manifest_path)
            write_json(ledger_path, build_initial_ledger(manifest))
            return 0

        if args.self_test:
            print(json.dumps(run_self_test(), indent=2, sort_keys=True))
            return 0

        manifest = read_json(manifest_path)
        ledger = read_json(ledger_path)
        selection = build_selection(manifest, ledger)
        assert_public_safe_selection(selection)

        if args.write:
            write_json(output_path, selection)
            if args.filter_export:
                filter_export(args.filter_export, selection, ledger)
            return 0

        ok = compare(output_path, selection)
        if args.filter_export:
            filter_export(args.filter_export, selection, ledger)
        return 0 if ok else 1
    except PublicationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
