//! CLIPS+LLM Hybrid Example
//!
//! Demonstrates combining CLIPS expert system with LLM for superior results:
//! - LLM preprocesses unstructured input into structured facts
//! - CLIPS applies deterministic business rules
//! - LLM postprocesses for human-friendly output
//!
//! ## Interactive Modes
//!
//! - `--verbose` or `-v`: Show raw HTTP request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! Environment variables:
//! - `NXUSKIT_VERBOSE=1`: Enable verbose mode
//! - `NXUSKIT_STEP=1`: Enable step mode

use clips_llm_hybrid::analyze_ticket;
use nxuskit::builders::OllamaProvider;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::path::Path;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    println!("=== CLIPS+LLM Hybrid Demo ===\n");
    println!("This example demonstrates the hybrid AI pattern:");
    println!("1. LLM classifies ticket (category, priority, sentiment, entities)");
    println!("2. CLIPS applies deterministic routing rules (team, SLA, escalation)");
    println!("3. LLM generates empathetic response suggestion\n");

    if config.step_pause(
        "Creating Ollama provider...",
        &[
            "This initializes the HTTP client for Ollama",
            "Connects to the local Ollama server at http://localhost:11434",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let provider = OllamaProvider::builder()
        .base_url("http://localhost:11434")
        .build()?;

    let tickets = vec![
        (
            "Security Incident",
            "URGENT: We've detected unauthorized access attempts on our production database. Multiple failed login attempts from unknown IPs. Need immediate investigation!",
        ),
        (
            "Infrastructure Issue",
            "Database connection timeouts are causing checkout failures. Customers are complaining they can't complete purchases. This started after last night's deployment.",
        ),
        (
            "Application Bug",
            "The login button on the mobile app is not responding. Users have to force close and reopen the app. Started happening after the latest update.",
        ),
        (
            "General Inquiry",
            "Hi, I was wondering if you could help me understand how to export my data? The documentation is a bit unclear.",
        ),
    ];

    for (label, ticket_text) in tickets {
        println!("=== {} ===", label);
        println!("Ticket: {}...\n", &ticket_text[..ticket_text.len().min(80)]);

        if config.step_pause(
            "Analyzing ticket with hybrid pipeline...",
            &[
                "Step 1: LLM classifies the ticket (category, priority, sentiment)",
                "Step 2: CLIPS applies deterministic routing rules",
                "Step 3: LLM generates suggested response",
            ],
        ) == StepAction::Quit
        {
            return Ok(());
        }

        // Show request in verbose mode
        config.print_request(
            "POST",
            "http://localhost:11434/api/chat",
            &serde_json::json!({
                "model": "llama3",
                "ticket_preview": &ticket_text[..ticket_text.len().min(50)],
                "pipeline": "hybrid-clips-llm"
            }),
        );

        // Rules file is in parent directory (shared between Rust and Go implementations)
        let rules_path = Path::new("../ticket-routing.clp");
        let start = std::time::Instant::now();
        match analyze_ticket(&provider, "llama3", ticket_text, rules_path).await {
            Ok(analysis) => {
                let elapsed_ms = start.elapsed().as_millis() as u64;
                // Show response in verbose mode
                config.print_response(
                    200,
                    elapsed_ms,
                    &serde_json::json!({
                        "team": &analysis.team,
                        "sla_hours": analysis.sla_hours,
                        "escalation_level": analysis.escalation_level,
                        "sentiment": &analysis.sentiment
                    }),
                );

                println!("Routing (from CLIPS rules - deterministic):");
                println!("  Team: {}", analysis.team);
                println!("  SLA: {} hours", analysis.sla_hours);
                println!("  Escalation: Level {}", analysis.escalation_level);
                println!();
                println!("Analysis (from LLM - probabilistic):");
                println!("  Sentiment: {}", analysis.sentiment);
                println!("  Key Entities: {:?}", analysis.key_entities);
                println!();
                println!("Suggested Response:");
                println!("  {}", analysis.suggested_response);
            }
            Err(e) => {
                println!("Analysis failed: {:?}", e);
            }
        }
        println!("\n{}\n", "-".repeat(60));
    }

    println!("=== Why Hybrid is Better ===");
    println!("- LLM alone: May miss SLA policies, inconsistent routing");
    println!("- CLIPS alone: Can't understand natural language input");
    println!("- CLIPS + LLM: Best of both - understanding AND policy compliance");

    Ok(())
}
