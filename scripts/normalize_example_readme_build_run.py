#!/usr/bin/env python3
"""Normalize example READMEs toward examples/EXAMPLE_README_TEMPLATE.md.

- **What this demonstrates** / **Prerequisites** from `conformance/examples_manifest.json`
- **Build** / **Run** (SDK blurb, heading renames, Library usage)

Idempotent. Re-run after manifest edits.

Usage (repo root):
  python3 scripts/normalize_example_readme_build_run.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def ex_root_from_impl(rel: str) -> Path:
    p = Path(rel)
    if p.parts[-1] in ("rust", "go", "python", "core", "cli", "egui"):
        return p.parent
    return p


def collect_readme_data(
    manifest: dict, root: Path
) -> dict[str, tuple[set[str], Path, dict]]:
    """readme absolute path -> (langs, example root path, manifest example object)."""
    out: dict[str, tuple[set[str], Path, dict]] = {}
    for ex in manifest["examples"]:
        for lang, rel in ex.get("implementations", {}).items():
            er = (root / ex_root_from_impl(rel)).resolve()
            readme = er / "README.md"
            if readme.is_file():
                k = str(readme.resolve())
                langs, _, _ = out.get(k, (set(), er, ex))
                langs = langs | {lang}
                out[k] = (langs, er, ex)
    return out


def readme_to_root_rel(readme: Path, root: Path) -> str:
    n = len(readme.relative_to(root).parts) - 1
    return ("../" * n) + "README.md"


def go_build_line_fixed(ex_root: Path, *, nested_in_go_readme: bool) -> str:
    go = ex_root / "go"
    if not go.is_dir():
        return ""
    if nested_in_go_readme:
        if (go / "Makefile").is_file():
            return "make build"
        return "mkdir -p bin && CGO_ENABLED=1 go build -tags nxuskit -o bin/ ./..."
    if (go / "Makefile").is_file():
        return "cd go && make build"
    return "cd go && mkdir -p bin && CGO_ENABLED=1 go build -tags nxuskit -o bin/ ./..."


def build_markdown(
    langs: set[str],
    readme_link: str,
    ex_root: Path,
    readme: Path,
    root: Path,
) -> str:
    readme_dir = readme.parent
    nested_go = readme_dir.resolve() == (ex_root / "go").resolve()
    sibling_doc = (
        readme_dir.parent.resolve() == ex_root.resolve()
        and readme_dir.name not in ("rust", "go", "python")
    )
    ex_dir_display = "/" + str(readme_dir.relative_to(root)).replace("\\", "/")

    lines = [
        "## Build",
        "",
        "Attach an **installed SDK** (`NXUSKIT_SDK_DIR`: extracted bundle or installer layout). See "
        f"the repository [README.md]({readme_link}) and `scripts/test-examples.sh`.",
        "",
        "```bash",
        f"# From `{ex_dir_display}`:",
    ]
    if "rust" in langs:
        rust_dir = ex_root / "rust"
        if rust_dir.is_dir():
            if readme_dir.resolve() == rust_dir.resolve():
                lines.append("cargo build")
            elif sibling_doc:
                lines.append("cd ../rust && cargo build")
            elif nested_go:
                lines.append("cd ../rust && cargo build")
            else:
                lines.append("cd rust && cargo build")
        elif (readme_dir / "Cargo.toml").is_file():
            lines.append("cargo build")
        elif (ex_root / "Cargo.toml").is_file():
            lines.append("cargo build")
    if "go" in langs:
        g = go_build_line_fixed(ex_root, nested_in_go_readme=nested_go)
        if g:
            lines.append(g)
    if "python" in langs and (ex_root / "python").is_dir():
        if nested_go:
            lines.append("cd ../python && python3 main.py --help")
        elif sibling_doc:
            lines.append("cd ../python && python3 main.py --help")
        else:
            lines.append("cd python && python3 main.py --help")
    lines.extend(["```", "", ""])
    return "\n".join(lines)


def insert_after_heading_table(text: str, heading: str, insert: str) -> str | None:
    marker = f"## {heading}\n"
    if marker not in text:
        return None
    pre, rest = text.split(marker, 1)
    lines = rest.splitlines(keepends=True)
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or not lines[i].lstrip().startswith("|"):
        return pre + marker + insert + "".join(lines)
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        i += 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    return pre + marker + "".join(lines[:i]) + insert + "".join(lines[i:])


def insert_before_heading(text: str, target_heading: str, insert: str) -> str | None:
    m = f"## {target_heading}\n"
    if m not in text:
        return None
    return text.replace(m, insert + m, 1)


def usage_body_is_shell_only(text: str) -> bool:
    if "## Usage\n" not in text:
        return False
    rest = text.split("## Usage\n", 1)[1]
    before_next = rest.split("\n## ", 1)[0]
    if "```rust" in before_next or "```go" in before_next:
        return False
    return "```bash" in before_next or "```sh" in before_next


DIFFICULTY_ICONS = {
    "starter": "🟢",
    "intermediate": "🟡",
    "advanced": "🏁",
}


def _difficulty_badge_line(ex: dict) -> str:
    """Build the difficulty badge line for 'What this demonstrates'."""
    difficulty = ex.get("difficulty", "")
    if not difficulty:
        return ""
    icon = DIFFICULTY_ICONS.get(difficulty, "")
    tags = ex.get("tech_tags") or []
    tag_str = " · ".join(tags) if tags else ""
    label = difficulty.capitalize()
    return f"**Difficulty: {label}** {icon} · {tag_str}\n\n"


def _insert_or_update_difficulty_badge(text: str, ex: dict) -> str:
    """Insert or replace the difficulty badge inside 'What this demonstrates'."""
    difficulty = ex.get("difficulty")
    if not difficulty:
        return text

    badge_line = _difficulty_badge_line(ex)
    if not badge_line:
        return text

    # Find the "## What this demonstrates" heading
    marker = "## What this demonstrates\n"
    if marker not in text:
        return text

    before, after = text.split(marker, 1)

    # Remove any existing difficulty badge line (starts with **Difficulty:)
    lines = after.split("\n")
    filtered = []
    skip_blank_after_badge = False
    for line in lines:
        if line.startswith("**Difficulty:"):
            skip_blank_after_badge = True
            continue
        if skip_blank_after_badge and line.strip() == "":
            skip_blank_after_badge = False
            continue
        skip_blank_after_badge = False
        filtered.append(line)

    after = "\n".join(filtered)

    # Insert badge after the heading (skip leading blank line)
    if after.startswith("\n"):
        return before + marker + "\n" + badge_line + after[1:]
    return before + marker + "\n" + badge_line + after


def manifest_demonstrates_prerequisites(
    text: str,
    ex: dict,
    langs: set[str],
    readme: Path,
    root: Path,
) -> str:
    """Insert ## What this demonstrates / ## Prerequisites when missing."""
    has_what = (
        "## What this demonstrates\n" in text or "## What this demonstrates\r\n" in text
    )
    has_prereq = "## Prerequisites\n" in text or "## Prerequisites\r\n" in text

    if has_what:
        what_block = ""
    else:
        tags = ex.get("tech_tags") or []
        tag_note = ", ".join(f"`{t}`" for t in tags) if tags else "(none)"
        badge = _difficulty_badge_line(ex)
        what_block = (
            "## What this demonstrates\n\n"
            + badge
            + f"- **Summary:** {ex['description']}\n"
            f"- **Scenario:** {ex['scenario']}\n"
            f"- **`tech_tags` in manifest:** {tag_note} — example id **`{ex['name']}`** in `conformance/examples_manifest.json`.\n\n"
        )

    if has_prereq:
        prereq_block = ""
    else:
        rlink = readme_to_root_rel(readme, root)
        LANG_ORDER = {"rust": 0, "go": 1, "python": 2, "bash": 3}
        lang_list = ", ".join(sorted(langs, key=lambda lang: LANG_ORDER.get(lang, 99)))
        prereq_lines = [
            "## Prerequisites",
            "",
            f"- **SDK:** Use an installed tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` wires Go/Rust/Python deps from that tree only — see [README.md]({rlink}), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.",
        ]
        if lang_list:
            prereq_lines.append(
                f"- **Languages in this example:** {lang_list} (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**)."
            )
        tags = set(ex.get("tech_tags") or [])
        if "LLM" in tags or "Vision" in tags or "Streaming" in tags:
            prereq_lines.append(
                "- **Models:** Set cloud provider API keys and/or run **Ollama** locally when you execute the **Run** steps (interactive flags like `--help` / `--verbose` are documented below)."
            )
        if "CLIPS" in tags:
            prereq_lines.append(
                "- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs."
            )
        if "MCP" in tags:
            prereq_lines.append(
                "- **MCP:** Running the full workflow may require an MCP-capable host or fixture data as noted in the integration README."
            )
        prereq_block = "\n".join(prereq_lines) + "\n\n"

    if not what_block and not prereq_block:
        return text

    combined = what_block + prereq_block
    if not combined:
        return text

    anchors = (
        "Key nxusKit Features Demonstrated",
        "CLIPS integration path",
        "Real-World Application",
        "Requirements",
        "Overview",
        "Pattern Overview",
        "Pipeline Architecture",
        "Supported Puzzles",
        "Languages",
        "Language Implementations",
        "Technologies",
        "Build",
        "Features",
        "Example Queries",
    )
    for a in anchors:
        trial = insert_before_heading(text, a, combined)
        if trial:
            return trial

    if "## Edition\n" in text:
        parts = text.split("## Edition\n", 1)
        body = parts[1]
        lines = body.splitlines(keepends=True)
        j = 0
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        while j < len(lines) and lines[j].strip() != "":
            j += 1
        if j < len(lines):
            j += 1
        return (
            parts[0]
            + "## Edition\n"
            + "".join(lines[:j])
            + combined
            + "".join(lines[j:])
        )

    return text


def insert_tagline_blockquote(text: str, tagline: str | None) -> str:
    """Insert or replace a tagline blockquote between the H1 and first H2.

    The blockquote is a single line starting with '> ' placed after the H1
    heading and before the first H2 heading. If a blockquote already exists
    in that region, it is replaced. If tagline is None or empty, any existing
    blockquote in that region is removed.
    """
    lines = text.split("\n")
    h1_idx = None
    first_h2_idx = None

    for i, line in enumerate(lines):
        if h1_idx is None and line.startswith("# "):
            h1_idx = i
        elif h1_idx is not None and line.startswith("## "):
            first_h2_idx = i
            break

    if h1_idx is None:
        return text  # No H1 found — don't touch

    if first_h2_idx is None:
        first_h2_idx = len(lines)

    # Find and remove any existing blockquote lines between H1 and first H2
    region_start = h1_idx + 1
    new_lines = list(lines[:region_start])
    for i in range(region_start, first_h2_idx):
        if not lines[i].startswith("> ") and lines[i] != ">":
            new_lines.append(lines[i])
    # Remove trailing blank lines from the region before H2
    while new_lines and new_lines[-1].strip() == "" and len(new_lines) > region_start:
        new_lines.pop()

    # Insert the tagline blockquote if we have one
    if tagline:
        new_lines.append("")
        new_lines.append(f"> {tagline}")

    new_lines.append("")
    new_lines.extend(lines[first_h2_idx:])
    return "\n".join(new_lines)


def insert_scenarios_line(text: str, scenarios: list[dict]) -> str:
    """Insert or replace a **Scenarios**: line between tagline and first H2.

    For examples with a scenarios array, inserts a line like:
        **Scenarios**: `maze-rat` · `potion` · `food-truck`

    Idempotent: removes any existing **Scenarios**: line before inserting.
    Skips insertion if scenarios is empty.
    """
    lines = text.split("\n")
    h1_idx = None
    first_h2_idx = None

    for i, line in enumerate(lines):
        if h1_idx is None and line.startswith("# "):
            h1_idx = i
        elif h1_idx is not None and line.startswith("## "):
            first_h2_idx = i
            break

    if h1_idx is None:
        return text

    if first_h2_idx is None:
        first_h2_idx = len(lines)

    # Remove any existing **Scenarios**: line and collapse consecutive blanks
    region_start = h1_idx + 1
    new_lines = list(lines[:region_start])
    for i in range(region_start, first_h2_idx):
        if lines[i].startswith("**Scenarios**:"):
            continue
        # Collapse consecutive blank lines
        if not lines[i].strip() and new_lines and not new_lines[-1].strip():
            continue
        new_lines.append(lines[i])

    # Insert the scenarios line if we have scenarios
    if scenarios:
        names = [f"`{s['name']}`" for s in scenarios]
        scenarios_line = f"**Scenarios**: {' · '.join(names)}"

        # Insert after tagline blockquote (or after H1 + blank line)
        insert_idx = len(new_lines)
        # Find the blockquote if it exists
        for i in range(region_start, len(new_lines)):
            if new_lines[i].startswith("> "):
                insert_idx = i + 1
                break

        # Ensure blank line before scenarios line
        if insert_idx < len(new_lines) and new_lines[insert_idx - 1].strip():
            new_lines.insert(insert_idx, "")
            insert_idx += 1

        new_lines.insert(insert_idx, scenarios_line)

    # Ensure blank line before H2
    while (
        new_lines and new_lines[-1].strip() == "" and len(new_lines) > region_start + 1
    ):
        new_lines.pop()
    new_lines.append("")

    new_lines.extend(lines[first_h2_idx:])
    return "\n".join(new_lines)


def transform_text(
    text: str,
    langs: set[str],
    ex_root: Path,
    root: Path,
    readme: Path,
    ex: dict | None,
) -> str:
    if ex is not None:
        text = insert_tagline_blockquote(text, ex.get("tagline"))
        text = insert_scenarios_line(text, ex.get("scenarios", []))
        text = manifest_demonstrates_prerequisites(text, ex, langs, readme, root)
        text = _insert_or_update_difficulty_badge(text, ex)

    rlink = readme_to_root_rel(readme, root)
    build_md = build_markdown(langs, rlink, ex_root, readme, root)

    if "## Build\n" not in text and "## Build\r\n" not in text:
        inserted = None
        for h in ("Language Implementations", "Languages"):
            if f"## {h}\n" in text:
                inserted = insert_after_heading_table(text, h, build_md)
                if inserted:
                    break
        if inserted is None:
            for before in (
                "Quick Start",
                "Running the Examples",
                "Running",
                "Installation",
                "Usage",
            ):
                trial = insert_before_heading(text, before, build_md)
                if trial:
                    inserted = trial
                    break
        if inserted is not None:
            text = inserted

    text = text.replace("## Running the Examples\n", "## Run\n")
    if "## Run\n" not in text:
        text = text.replace("## Running\n", "## Run\n")
    if "## Run\n" not in text:
        text = text.replace("## Quick Start\n", "## Run\n")
    if "## Run\n" not in text and usage_body_is_shell_only(text):
        text = text.replace("## Usage\n", "## Run\n", 1)

    if "## Usage\n" in text and "## Run\n" in text:
        between = text.split("## Usage\n", 1)[1].split("## Run\n", 1)[0]
        if "```rust" in between or "```go" in between:
            text = text.replace("## Usage\n", "## Library usage\n", 1)

    return text


def patch_auth_helper_cli(text: str, root: Path) -> str:
    readme = root / "examples/apps/auth-helper/cli/README.md"
    rlink = readme_to_root_rel(readme, root)
    replacement = f"""## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md]({rlink}).

1. Build the nxusKit SDK (static-link) if needed:

```bash
cd ../../../../
cargo build --release -p nxuskit-core
```

2. Build this CLI from `examples/apps/auth-helper/cli`:

```bash
cargo build --release
```

## Run

```bash
cargo run -- status
```

"""
    if "## Setup (< 5 minutes)" in text:
        text = text.replace(
            "## Setup (< 5 minutes)\n\n1. Build the nxusKit SDK (static-link):\n"
            "   ```bash\n"
            "   cd ../../../../\n"
            "   cargo build --release -p nxuskit-core\n"
            "   ```\n\n"
            "2. Build and run:\n"
            "   ```bash\n"
            "   cargo run -- status\n"
            "   ```\n\n",
            replacement,
        )
    return text


def patch_auth_helper_egui(text: str, root: Path) -> str:
    readme = root / "examples/apps/auth-helper/egui/README.md"
    rlink = readme_to_root_rel(readme, root)
    replacement = f"""## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md]({rlink}).

1. Build the nxusKit SDK (static-link) if needed:

```bash
cd ../../../../
cargo build --release -p nxuskit-core
```

2. Build this app from `examples/apps/auth-helper/egui`:

```bash
cargo build --release
```

## Run

```bash
cargo run
```

"""
    if "## Setup (< 5 minutes)" in text:
        text = text.replace(
            "## Setup (< 5 minutes)\n\n1. Build the nxusKit SDK (static-link):\n"
            "   ```bash\n"
            "   cd ../../../../\n"
            "   cargo build --release -p nxuskit-core\n"
            "   ```\n\n"
            "2. Build and run:\n"
            "   ```bash\n"
            "   cargo run\n"
            "   ```\n\n",
            replacement,
        )
    return text


def main() -> int:
    dry = "--dry-run" in sys.argv
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "conformance/examples_manifest.json").read_text(encoding="utf-8")
    )
    readme_data = collect_readme_data(manifest, root)

    for app_readme in (root / "examples/apps").glob("*/README.md"):
        p = app_readme.parent
        go_readme = p / "go" / "README.md"
        if go_readme.is_file() and str(go_readme.resolve()) not in readme_data:
            langs, er, ex = readme_data[str(app_readme.resolve())]
            readme_data[str(go_readme.resolve())] = (langs, er, ex)

    auth_ex = next(e for e in manifest["examples"] if e["name"] == "auth-helper")
    ah = root / "examples/apps/auth-helper"
    for sub in ("cli", "egui"):
        r = ah / sub / "README.md"
        if r.is_file():
            readme_data[str(r.resolve())] = ({"rust"}, (ah / sub).resolve(), auth_ex)

    clips_ex = next(e for e in manifest["examples"] if e["name"] == "clips-basics")
    clips_readme = root / "examples/integrations/clips-basics/clips/README.md"
    if clips_readme.is_file():
        readme_data[str(clips_readme.resolve())] = (
            {"rust"},
            root / "examples/integrations/clips-basics",
            clips_ex,
        )

    skip = {
        root / "examples/README.md",
    }

    changed = 0
    for readme_str, (langs, ex_root, ex) in sorted(readme_data.items()):
        readme = Path(readme_str)
        if readme in skip:
            continue
        orig = readme.read_text(encoding="utf-8")
        text = transform_text(orig, langs, ex_root, root, readme, ex)
        if (
            readme.resolve()
            == (root / "examples/apps/auth-helper/cli/README.md").resolve()
        ):
            text = patch_auth_helper_cli(text, root)
        if (
            readme.resolve()
            == (root / "examples/apps/auth-helper/egui/README.md").resolve()
        ):
            text = patch_auth_helper_egui(text, root)

        if text != orig:
            print("M", readme.relative_to(root))
            changed += 1
            if not dry:
                readme.write_text(text, encoding="utf-8")

    print(f"{'Would change' if dry else 'Updated'} {changed} file(s).")
    if dry and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
