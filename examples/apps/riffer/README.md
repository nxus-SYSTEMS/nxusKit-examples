# Riffer - Music Sequence Analysis and Transformation (Rust)

A command-line tool for analyzing and transforming music sequences, implemented in Rust.

> Analyze, score, and transform MIDI and MusicXML sequences using CLIPS rule-based music theory and LLM-powered narrative and transformation.

**Scenarios**: `analyze` · `score` · `transform` · `convert`

## Edition

**Pro** — requires a Pro (or trial) entitlement.

## What this demonstrates

**Difficulty: Advanced** 🏁 · LLM · CLIPS

- **Summary:** CLIPS rule-based music composition engine
- **Scenario:** Generate musical riffs using CLIPS composition rules
- **`tech_tags` in manifest:** `CLIPS` — example id **`riffer`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## Real-World Application

Algorithmic music generation, creative AI assistant.

## Requirements

**Edition**: nxusKit Pro  
This example requires the Pro edition of nxusKit. [Purchase Pro](https://nxus.systems/pro) or start a free 30-day trial (automatic on first Pro feature call).

## Technologies

CLIPS

## Language Implementations

| Language | Path | Status |
|----------|------|--------|
| Rust | `rust/` | Available |
| Go | `go/` | Available |

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/riffer`:
cd rust && cargo build
cd go && make build
```
## Features

- **Analyze** - Detect key signature, analyze intervals, contour, rhythm, and dynamics
- **Score** - 6-dimension musicality scoring with improvement suggestions
- **Transform** - Transpose, invert, retrograde, augment, diminish, change key/tempo
- **Convert** - Convert between MIDI and MusicXML formats

## Installation

```bash
cd examples/apps/riffer/rust
cargo build --release
```

Find and set the binary path:

```bash
# Find where cargo built the binary
RIFFER=$(cargo metadata --format-version 1 | sed -n 's/.*"target_directory":"\([^"]*\)".*/\1/p')/release/riffer

# Verify it exists
ls -la "$RIFFER"
```

## Run

From the `examples/apps/riffer/rust` directory:

### Analyze a sequence

```bash
# JSON output (default)
"$RIFFER" analyze -i ../shared/testdata/e_minor_riff.mid

# Markdown output
"$RIFFER" analyze -i ../shared/testdata/e_minor_riff.mid -f markdown
```

### Score musicality

```bash
# Get a 6-dimension score with suggestions
"$RIFFER" score -i ../shared/testdata/e_minor_riff.mid -f markdown
```

Output includes:
- Overall score (0-100)
- Dimension scores: Harmonic Coherence, Melodic Interest, Rhythmic Variety, Resolution Quality, Dynamics Expression, Structural Balance
- Improvement suggestions

### Transform a sequence

```bash
# Transpose up 5 semitones
$RIFFER transform -i input.mid -o output.mid --transpose 5

# Invert around middle C (MIDI note 60)
$RIFFER transform -i input.mid -o output.mid --invert 60

# Reverse notes (retrograde)
$RIFFER transform -i input.mid -o output.mid --retrograde

# Rhythmic augmentation - double note durations (not to be confused with augmented chords)
$RIFFER transform -i input.mid -o output.mid --augment 2.0

# Rhythmic diminution - halve note durations (not to be confused with diminished chords)
$RIFFER transform -i input.mid -o output.mid --diminish 2.0

# Change key to G major
$RIFFER transform -i input.mid -o output.mid --key G

# Change tempo to 140 BPM
$RIFFER transform -i input.mid -o output.mid --tempo 140

# Combine multiple transformations
$RIFFER transform -i input.mid -o output.mid --transpose 5 --tempo 140
```

### Convert between formats

```bash
# MIDI to MusicXML
$RIFFER convert -i input.mid -o output.xml

# MusicXML to MIDI
$RIFFER convert -i input.xml -o output.mid
```

## Supported Formats

- **MIDI** (.mid, .midi) - Standard MIDI File format
- **MusicXML** (.xml, .musicxml) - MusicXML partwise format

## Interactive Modes

All examples support debugging flags:

```bash
# Verbose mode - show raw HTTP request/response data
cargo run -- --verbose      # Rust
./bin/riffer --verbose       # Go

# Step mode - pause at each step with explanations
cargo run -- --step         # Rust
./bin/riffer --step          # Go

# Combined mode
cargo run -- --verbose --step
```

Or use environment variables:
```bash
export NXUSKIT_VERBOSE=1
export NXUSKIT_STEP=1
```

## Example Output

### Analysis (Markdown)

```markdown
# Music Analysis: c_major_scale

## Summary
- **Notes**: 8
- **Duration**: 3840 ticks

## Key Detection
- **Detected Key**: C Major
- **Confidence**: 96.7%

## Scale Analysis
- **In Scale**: 8 notes
- **Out of Scale**: 0 notes
- **Harmonic Coherence**: 100.0%
```

### Score (Markdown)

```markdown
# Music Score: c_major_scale

## Overall Score: 59.3/100 (fair)

## Dimension Scores
| Dimension | Score | Rating |
|-----------|-------|--------|
| Harmonic Coherence | 100.0 | excellent |
| Melodic Interest | 39.0 | poor |
| Rhythmic Variety | 20.0 | poor |

## Suggestions for Improvement
- Add more interval variety for melodic interest
- Add rhythmic variety with different note durations
```

## Architecture

```
riffer/
├── main.rs           # CLI entry point
├── types.rs          # Core data types (Note, Sequence, etc.)
├── errors.rs         # Error handling
├── formats/
│   ├── midi.rs       # MIDI read/write
│   └── musicxml.rs   # MusicXML read/write
├── theory/
│   ├── intervals.rs  # Interval classification
│   ├── keys.rs       # Key detection (Krumhansl-Schmuckler)
│   └── scales.rs     # Scale definitions
└── engine/
    ├── analyzer.rs   # Sequence analysis
    ├── scorer.rs     # 6-dimension scoring
    ├── transformer.rs # Transformations
    └── clips_bridge.rs # CLIPS rule engine (ClipsProvider)
```

## Testing

```bash
cd examples/apps/riffer/rust
cargo test
```

## License

Part of the nxusKit project.
