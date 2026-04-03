#!/usr/bin/env python3
"""CI lint: verify manifest languages and tech_tags are in canonical order."""

import json
import sys
from pathlib import Path

CANONICAL_LANGS = ["rust", "go", "python"]
CANONICAL_TAGS = ["LLM", "CLIPS", "Solver", "BN", "ZEN", "MCP", "Vision", "Streaming", "Auth", "OAuth"]

def check_order(items: list[str], canonical: list[str], label: str, name: str) -> list[str]:
    """Return error strings if items are not in canonical subsequence order."""
    indices = []
    for item in items:
        if item in canonical:
            indices.append(canonical.index(item))
        # unknown items get appended at end — no ordering constraint on them
    if indices != sorted(indices):
        expected = sorted(items, key=lambda x: canonical.index(x) if x in canonical else 999)
        return [f"  {name}: {label} {items} should be {expected}"]
    return []

def main() -> int:
    manifest_path = Path(__file__).resolve().parent.parent / "conformance" / "examples_manifest.json"
    with open(manifest_path) as f:
        data = json.load(f)

    errors: list[str] = []
    for ex in data["examples"]:
        name = ex["name"]
        errors.extend(check_order(ex.get("languages", []), CANONICAL_LANGS, "languages", name))
        errors.extend(check_order(ex.get("tech_tags", []), CANONICAL_TAGS, "tech_tags", name))

    if errors:
        print(f"Canonical ordering violations ({len(errors)}):")
        print("\n".join(errors))
        print(f"\nCanonical languages: {CANONICAL_LANGS}")
        print(f"Canonical tech_tags: {CANONICAL_TAGS}")
        return 1

    print(f"All {len(data['examples'])} examples have canonical ordering.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
