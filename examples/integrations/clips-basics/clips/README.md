# CLIPS Provider Examples

This directory contains examples demonstrating the CLIPS (C Language Integrated Production System) provider for nxuskit. CLIPS enables rule-based expert system inference as an alternative to LLM-based reasoning.

> Bring deterministic rule-based logic to your applications by driving the CLIPS inference engine directly through the nxusKit SDK.

## Edition

## What this demonstrates

**Difficulty: Intermediate** 🟦 · CLIPS

- **Summary:** CLIPS rule engine basics via nxusKit SDK
- **Scenario:** Load rules, assert facts, and run the CLIPS inference engine
- **`tech_tags` in manifest:** `CLIPS` — example id **`clips-basics`** in `conformance/examples_manifest.json`.

## Prerequisites

- **SDK:** Use an installed SDK tree (`NXUSKIT_SDK_DIR`, `NXUSKIT_LIB_PATH` as needed); `test-examples.sh` resolves Go/Rust/Python deps from that tree only — see [README.md](../../../../README.md), `scripts/setup-sdk.sh`, and `scripts/test-examples.sh`.
- **Languages in this example:** rust (paths under this directory; Python may live under a sibling `python/` or shared reference per **Language Implementations**).
- **CLIPS:** Use an SDK build with CLIPS support (native `libnxuskit`); rule files and JSON contracts are referenced from this repo’s `conformance/` docs.

**Community** — runs on the OSS / Community SDK edition (same tier as the parent **clips-basics** example).

## Build

Attach an **installed SDK** (`NXUSKIT_SDK_DIR`). See the repository [README.md](../../../../README.md) and `scripts/test-examples.sh`.

```bash
# From `/examples/integrations/clips-basics/clips`:
cd ../rust && cargo build
```

## Run

```bash
# Run the overview example (lists all features and runs a quick demo)
cargo run --example clips_example --features clips

# Run individual examples
cargo run --example clips_animal_classification --features clips
cargo run --example clips_medical_triage --features clips
cargo run --example clips_inventory --features clips
cargo run --example clips_scheduler --features clips

# Run the multi-stage pipeline example
cargo run --example clips_pipeline --features clips
```

## Examples Overview

| Example | Description | Key Features |
|---------|-------------|--------------|
| `clips_example` | Overview and feature tour | Lists available rule bases, quick classification demo |
| `clips_animal_classification` | Classify animals by characteristics | Basic CLIPS usage, JSON input |
| `clips_medical_triage` | Patient prioritization | **ThinkingMode** (trace visibility) |
| `clips_inventory` | Stock management system | **JSON file loading**, real-world domain |
| `clips_scheduler` | Task scheduling with dependencies | **Streaming modes** (Fact, Rule) |
| `clips_pipeline` | Multi-stage rule pipelines | **Chained rulebases**, linear & branching flows |

## Directory Structure

```
shared/
├── clips/
│   ├── README.md              # This file
│   └── PIPELINE_CONVENTION.md # Convention for composable pipelines
├── rules/                     # CLIPS rule files (.clp)
│   ├── animal-classification.clp
│   ├── medical-triage.clp
│   ├── inventory-management.clp
│   ├── task-scheduler.clp
│   └── pipeline/              # Pipeline example rule files
│       ├── common.clp         # Shared pipeline templates
│       ├── order-validation.clp
│       ├── order-pricing.clp
│       ├── order-fulfillment.clp
│       ├── incident-detection.clp
│       ├── incident-classification.clp
│       ├── incident-response-security.clp
│       ├── incident-response-ops.clp
│       └── incident-response-escalation.clp
├── data/                      # JSON fact files
│   ├── animals.json
│   ├── medical-cases.json
│   ├── inventory-scenario.json
│   ├── scheduler-scenario.json
│   └── pipeline/              # Pipeline scenario data
│       ├── orders.json        # Order processing scenarios
│       └── incidents.json     # Incident response scenarios
├── clips_example.rs
├── clips_animal_classification.rs
├── clips_medical_triage.rs
├── clips_inventory.rs
├── clips_scheduler.rs
└── clips_pipeline.rs          # Multi-stage pipeline runner
```

## Rule Bases

### animal-classification.clp
A simple educational example that classifies animals based on observable characteristics (backbone, body temperature, feathers, fur, scales, etc.).

**Templates:** `animal`, `classification`

**Example input:**
```json
{
  "facts": [{
    "template": "animal",
    "values": {
      "name": "Buddy",
      "has-backbone": {"symbol": "yes"},
      "body-temperature": {"symbol": "warm"},
      "has-fur": {"symbol": "yes"},
      "lays-eggs": {"symbol": "no"}
    }
  }]
}
```

**Example output:** Classifies as `mammal` with high confidence.

---

### medical-triage.clp
Prioritizes patients based on symptoms and vital signs. Demonstrates salience-based rule ordering for critical conditions.

**Templates:** `patient`, `vital-signs`, `symptom`, `medical-history`, `triage-priority`, `alert`

**Triage Levels:**
- Level 1: Immediate (resuscitation)
- Level 2: Emergent
- Level 3: Urgent
- Level 4: Less urgent
- Level 5: Non-urgent

**Note:** This is an educational example only, not for actual medical use.

---

### inventory-management.clp
Real-world inventory management with stock monitoring, reorder alerts, and dynamic pricing suggestions.

**Templates:** `product`, `inventory`, `incoming-shipment`, `sales-velocity`, `reorder-alert`, `stock-status`, `pricing-adjustment`, `warehouse-transfer`

**Features:**
- Stock level monitoring (out-of-stock, critical, low, adequate, overstocked)
- Automatic reorder recommendations
- Velocity-based pricing adjustments
- Multi-warehouse transfer suggestions

---

### task-scheduler.clp
Task scheduling with priorities, dependencies, and resource assignment.

**Templates:** `task`, `dependency`, `resource`, `schedule-entry`, `task-status-update`, `scheduling-alert`, `execution-order`

**Features:**
- Dependency resolution (marks tasks as ready/blocked)
- Priority calculation (high/medium/low)
- Resource assignment based on availability
- Deadline conflict detection
- Circular dependency detection

## Pipeline Examples

The `clips_pipeline` example demonstrates multi-stage rule processing where output from one rulebase becomes input for the next.

### Order Processing Pipeline (3-stage linear)
```
validation → pricing → fulfillment
```
- **validation**: Validates order completeness and business rules
- **pricing**: Applies discounts and calculates final totals
- **fulfillment**: Determines warehouse, carrier, and shipping

### Incident Response Pipeline (branching)
```
detection → classification → security/operations/escalation
```
- **detection**: Identifies incident type from raw events
- **classification**: Determines severity and response team
- **security/operations/escalation**: Team-specific response actions

See [PIPELINE_CONVENTION.md](PIPELINE_CONVENTION.md) for details on creating composable pipelines.

---

## Key Features Demonstrated

### 1. ThinkingMode (Trace Visibility)

Control whether rule firing traces are included in the output:

```rust
use nxuskit::ThinkingMode;

// Show trace (which rules fired)
let request = ChatRequest::new("rules.clp")
    .with_thinking_mode(ThinkingMode::Enabled);

// Hide trace (conclusions only)
let request = ChatRequest::new("rules.clp")
    .with_thinking_mode(ThinkingMode::Disabled);

// Auto (enables trace for CLIPS by default)
let request = ChatRequest::new("rules.clp")
    .with_thinking_mode(ThinkingMode::Auto);
```

See `clips_medical_triage.rs` for a complete example.

### 2. Streaming Modes

Control how results are chunked during streaming:

```json
{
  "facts": [...],
  "config": {
    "stream_mode": "fact"
  }
}
```

| Mode | Description |
|------|-------------|
| `default` | Single chunk with all results |
| `fact` | One chunk per derived fact |
| `rule` | One chunk per rule firing |

See `clips_scheduler.rs` for a complete example.

### 3. Loading Facts from JSON Files

```rust
use std::fs;

let json = fs::read_to_string("../../../shared/data/inventory-scenario.json")?;
let request = ChatRequest::new("inventory-management.clp")
    .with_message(Message::user(json));
```

See `clips_inventory.rs` for a complete example.

### 4. Persistent Mode

Keep facts across multiple chat requests:

```rust
let provider = ClipsProvider::builder()
    .rules_directory("./rules")
    .persistent(true)  // Facts persist between chats
    .build()?;

// Later, reset the environment
let reset_input = r#"{"command": "reset"}"#;
```

## JSON Input Format

```json
{
  "command": null,           // Optional: "reset" or "clear"
  "templates": [],           // Optional: auto-generate templates
  "facts": [                 // Required: facts to assert
    {
      "template": "template-name",
      "values": {
        "slot-name": "value",
        "symbol-slot": {"symbol": "symbol-value"},
        "number-slot": 42
      },
      "id": "optional-tracking-id"
    }
  ],
  "globals": {},             // Optional: global variable values
  "config": {                // Optional: request configuration
    "include_trace": true,
    "max_rules": 100,
    "stream_mode": "default",
    "output_templates": ["specific-template"],
    "derived_only_new": false
  }
}
```

## JSON Output Format

```json
{
  "conclusions": [           // Derived facts from inference
    {
      "template": "classification",
      "values": {...},
      "fact_index": 5,
      "derived": true
    }
  ],
  "input_facts": [],         // Echoed input facts (if requested)
  "trace": {                 // Execution trace (if enabled)
    "rules_fired": [...],
    "facts_asserted": [...],
    "facts_retracted": [...]
  },
  "stats": {
    "total_rules_fired": 3,
    "facts_asserted": 5,
    "conclusions_count": 2,
    "execution_time_ms": 1
  }
}
```

## Writing CLIPS Rules

Rules must use `deftemplate` (not COOL/defclass). Basic structure:

```clips
;;; Template definition
(deftemplate item
    "Description of the template"
    (slot name (type STRING))
    (slot value (type INTEGER) (default 0))
    (slot status (type SYMBOL) (allowed-symbols active inactive)))

;;; Rule definition
(defrule example-rule
    "Description of what this rule does"
    (declare (salience 50))  ; Optional: higher = fires first
    (item (name ?n) (value ?v&:(> ?v 100)))
    =>
    (assert (high-value-item (name ?n) (value ?v))))
```

## New Features (v0.6.0)

### Search Paths via `CLIPS_MODEL_PATH`

Set the `CLIPS_MODEL_PATH` environment variable to specify where CLIPS looks for rule files:

```bash
# Colon-separated paths (like PATH)
export CLIPS_MODEL_PATH="/opt/rules:/home/user/rules:./local-rules"

# Now you can use model names without full paths
cargo run --example clips_example --features clips
```

Search order:
1. Paths from `CLIPS_MODEL_PATH` (in order)
2. `rules_directory` from builder
3. Current directory as fallback

### Binary Loading (bload/bsave)

CLIPS automatically caches compiled rule bases for faster loading:

- On first load, source is loaded and binary is saved as `model.bin`
- On subsequent loads, if `model.bin` is newer than `model.clp`, binary is loaded
- Force source loading by specifying the `.clp` extension explicitly

### Help Command

Query available templates without running inference:

```rust
// List all templates in a rule base
let request = ChatRequest::new("medical-triage.clp")
    .with_message(Message::user("help"));

// Get JSON Schema for all templates
let request = ChatRequest::new("medical-triage.clp")
    .with_message(Message::user("help json"));

// Describe a specific template
let request = ChatRequest::new("medical-triage.clp")
    .with_message(Message::user("help patient"));
```

### Enhanced Model Listing

```rust
let models = provider.list_models().await?;
for model in models {
    // Shows: medical-triage
    //   📋 5 templates, ⚙️ 12 rules (s,b)
    //   Modified: 2 hours ago
    println!("{}", model.name);
    if let Some(desc) = model.description {
        println!("  {}", desc);
    }
}
```

### CLI Schema Conversion

Convert between CLIPS deftemplates and JSON Schema:

```bash
# Convert CLIPS to JSON Schema
cargo run --features clips -p nxuskit-cli -- schema to-json rules/medical-triage.clp

# Convert JSON Schema to CLIPS deftemplate
cargo run --features clips -p nxuskit-cli -- schema to-clips schema.json -o templates.clp
```

---

## Troubleshooting

**"CLIPS support not compiled"**
- Ensure you're using the `clips` feature: `--features clips`

**"Template not found"**
- Either define templates in your `.clp` file, or include them in the JSON input

**"File not found"**
- Run examples from the repository root directory
- Check the `rules_directory` path in the provider builder
- Or set `CLIPS_MODEL_PATH` environment variable

**Binary loading warnings**
- Binary files are automatically regenerated when source changes
- Delete `.bin` files to force source reload

## Further Reading

- [CLIPS Documentation](https://www.clipsrules.net/Documentation.html)
- [CLIPS User's Guide](https://www.clipsrules.net/documentation/v640/ug.pdf)
- [CLIPS Basic Programming Guide](https://www.clipsrules.net/documentation/v640/bpg.pdf)
