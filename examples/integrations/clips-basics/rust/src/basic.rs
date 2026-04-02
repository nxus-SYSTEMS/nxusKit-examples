//! Example: Using CLIPS Expert System Provider
//!
//! This is an overview example demonstrating the CLIPS provider capabilities.
//! For more detailed examples, see:
//!
//! - `clips_animal_classification.rs` - Basic animal classification
//! - `clips_medical_triage.rs` - Medical triage with thinking mode demo
//! - `clips_inventory.rs` - Inventory management with JSON file loading
//! - `clips_scheduler.rs` - Task scheduling with streaming mode demo
//!
//! Run with: cargo run --bin clips_basic
//!
//! ## Interactive Modes
//!
//! - `--verbose` or `-v`: Show raw HTTP request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! Environment variables:
//! - `NXUSKIT_VERBOSE=1`: Enable verbose mode
//! - `NXUSKIT_STEP=1`: Enable step mode

use nxuskit::{ChatRequest, Message, NxuskitProvider, ProviderConfig, ThinkingMode};
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::fs;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    println!("=== CLIPS Expert System Overview ===\n");

    if config.step_pause(
        "Creating CLIPS provider...",
        &[
            "CLIPS is an expert system shell for building rule-based systems",
            "The provider loads .clp rule files from the rules directory",
            "Trace output can be enabled for debugging rule execution",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Create CLIPS provider via NxuskitProvider with provider_type "clips"
    // The model field points to the rules directory
    let provider = NxuskitProvider::new(ProviderConfig {
        provider_type: "clips".to_string(),
        model: Some("../../../shared/rules".to_string()),
        ..Default::default()
    })?;

    // List available rule bases
    println!("--- Available Rule Bases ---\n");

    let models = provider.list_models()?;
    if models.is_empty() {
        println!("No .clp files found in rules directory");
        println!("Make sure you're running from the repository root.\n");
    } else {
        for model in &models {
            println!("  - {}", model.name);
        }
        println!();
    }

    // Quick demo: Animal classification from JSON file
    if config.step_pause(
        "Running animal classification demo...",
        &[
            "Loads animal data from JSON file",
            "CLIPS rules classify animals by their characteristics",
            "Results include classification and confidence level",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("--- Quick Demo: Animal Classification ---\n");

    let animals_path = Path::new("../../../shared/data/animals.json");
    if animals_path.exists() {
        let animals_json = fs::read_to_string(animals_path)?;
        let input: serde_json::Value = serde_json::from_str(&animals_json)?;

        let request = ChatRequest::new("animal-classification.clp")
            .with_message(Message::user(input.to_string()))
            .with_thinking_mode(ThinkingMode::Disabled);

        // Show request in verbose mode
        config.print_request(
            "CLIPS",
            "animal-classification.clp",
            &serde_json::json!({
                "rule_base": "animal-classification.clp",
                "thinking_mode": "disabled",
                "input": "animals.json"
            }),
        );

        let start = std::time::Instant::now();
        match provider.chat(request) {
            Ok(response) => {
                let elapsed_ms = start.elapsed().as_millis() as u64;
                // Show response in verbose mode
                config.print_response(
                    200,
                    elapsed_ms,
                    &serde_json::json!({
                        "content_length": response.content.len(),
                        "type": "CLIPS inference result"
                    }),
                );

                let output: serde_json::Value = serde_json::from_str(&response.content)?;

                if let Some(conclusions) = output.get("conclusions").and_then(|c| c.as_array()) {
                    let classifications: Vec<_> = conclusions
                        .iter()
                        .filter(|f| {
                            f.get("template").and_then(|t| t.as_str()) == Some("classification")
                        })
                        .collect();

                    println!("Classified {} animals:\n", classifications.len());
                    for c in classifications {
                        if let Some(values) = c.get("values") {
                            println!(
                                "  {} -> {} ({})",
                                values
                                    .get("animal-name")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("?"),
                                values
                                    .get("category")
                                    .and_then(|v| v.get("symbol"))
                                    .and_then(|s| s.as_str())
                                    .unwrap_or("?"),
                                values
                                    .get("confidence")
                                    .and_then(|v| v.get("symbol"))
                                    .and_then(|s| s.as_str())
                                    .unwrap_or("?")
                            );
                        }
                    }
                }

                if let Some(stats) = output.get("stats") {
                    println!(
                        "\nStats: {} rules fired, {} conclusions in {}ms",
                        stats
                            .get("total_rules_fired")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0),
                        stats
                            .get("conclusions_count")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0),
                        stats
                            .get("execution_time_ms")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0)
                    );
                }
            }
            Err(e) => {
                println!("Error running animal classification: {}", e);
                println!("(This is expected if CLIPS feature is not compiled)\n");
            }
        }
    } else {
        println!("Animals data file not found at: {}", animals_path.display());
        println!("Make sure you're running from the repository root.\n");
    }

    // Feature overview
    println!("\n--- CLIPS Provider Features ---\n");

    println!("1. RULE BASES (.clp files)");
    println!("   - animal-classification.clp: Classify animals by characteristics");
    println!("   - medical-triage.clp: Prioritize patients by symptoms and vitals");
    println!("   - inventory-management.clp: Stock alerts and reorder recommendations");
    println!("   - task-scheduler.clp: Task scheduling with dependencies\n");

    println!("2. THINKING MODE (Trace Visibility)");
    println!("   - ThinkingMode::Enabled: Show rule firing trace");
    println!("   - ThinkingMode::Disabled: Hide trace, conclusions only");
    println!("   - ThinkingMode::Auto: Enable trace for CLIPS (default)");
    println!("   See: clips_medical_triage for demo\n");

    println!("3. STREAMING MODES");
    println!("   - StreamMode::Default: Single response with all results");
    println!("   - StreamMode::Fact: One chunk per derived fact");
    println!("   - StreamMode::Rule: One chunk per rule firing");
    println!("   See: clips_scheduler for demo\n");

    println!("4. JSON DATA FILES");
    println!("   Load facts from .json files in data/ directory:");
    println!("   - data/animals.json: Animal characteristics");
    println!("   - data/medical-cases.json: Medical case scenarios");
    println!("   - data/inventory-scenario.json: Inventory state");
    println!("   - data/scheduler-scenario.json: Tasks and resources\n");

    println!("5. PERSISTENT MODE");
    println!("   - .persistent(true): Facts persist across chats");
    println!("   - Use 'reset' command to clear environment\n");

    println!("=== Run Individual Examples ===\n");
    println!("  cargo run --bin animal_classification");
    println!("  cargo run --bin medical_triage");
    println!("  cargo run --bin inventory");
    println!("  cargo run --bin scheduler\n");

    Ok(())
}
