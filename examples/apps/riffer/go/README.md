# Riffer - Music Sequence Analysis and Transformation (Go)

A command-line tool for analyzing and transforming music sequences, implemented in Go.

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

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** go, rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

## Features

- **Analyze** - Detect key signature, analyze intervals, contour, rhythm, and dynamics
- **Score** - 6-dimension musicality scoring with improvement suggestions
- **Transform** - Transpose, invert, retrograde, augment, diminish, change key/tempo
- **Convert** - Convert between MIDI and MusicXML formats

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/apps/riffer/go`:
cd ../rust && cargo build
make build
```
## Installation

```bash
cd packages/nxuskit-go/examples/riffer
go build -o riffer ./cmd/riffer
```

## Run

### Analyze a sequence

```bash
# JSON output (default)
riffer analyze -i input.mid

# Markdown output
riffer analyze -i input.mid -f markdown
```

### Score musicality

```bash
# Get a 6-dimension score with suggestions
riffer score -i input.mid -f markdown
```

Output includes:
- Overall score (0-100)
- Dimension scores: Harmonic Coherence, Melodic Interest, Rhythmic Variety, Resolution Quality, Dynamics Expression, Structural Balance
- Improvement suggestions

### Transform a sequence

```bash
# Transpose up 5 semitones
riffer transform -i input.mid -o output.mid --transpose 5

# Invert around first note
riffer transform -i input.mid -o output.mid --invert

# Invert around specific pitch (MIDI note 60)
riffer transform -i input.mid -o output.mid --invert-pivot 60

# Reverse notes (retrograde)
riffer transform -i input.mid -o output.mid --retrograde

# Double note durations (augment)
riffer transform -i input.mid -o output.mid --augment 2.0

# Halve note durations (diminish)
riffer transform -i input.mid -o output.mid --diminish 2.0

# Change key to G major
riffer transform -i input.mid -o output.mid --key G

# Change tempo to 140 BPM
riffer transform -i input.mid -o output.mid --tempo 140

# Combine multiple transformations
riffer transform -i input.mid -o output.mid --transpose 5 --tempo 140
```

### Convert between formats

```bash
# MIDI to MusicXML
riffer convert -i input.mid -o output.xml

# MusicXML to MIDI
riffer convert -i input.xml -o output.mid
```

## Supported Formats

- **MIDI** (.mid, .midi) - Standard MIDI File format
- **MusicXML** (.xml, .musicxml, .mxl) - MusicXML partwise format

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
├── cmd/riffer/main.go  # CLI entry point
├── types.go            # Core data types (Note, Sequence, etc.)
├── errors.go           # Error handling
├── midi.go             # MIDI read/write
├── musicxml.go         # MusicXML read/write
├── intervals.go        # Interval classification
├── keys.go             # Key detection (Krumhansl-Schmuckler)
├── scales.go           # Scale definitions
├── analyzer.go         # Sequence analysis
├── scorer.go           # 6-dimension scoring
├── transformer.go      # Transformations
└── clips_bridge.go     # CLIPS rule engine (ClipsProvider)
```

## Testing

```bash
go test ./...
```

## Parity with Rust

This Go implementation produces identical results to the Rust implementation:
- Same key detection algorithm (Krumhansl-Schmuckler)
- Same scoring dimensions and weights
- Same transformation operations
- Same MIDI/MusicXML format support

## License

Part of the nxusKit project.
