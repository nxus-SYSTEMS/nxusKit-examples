//! Example: Task Scheduler with CLIPS - Streaming Mode Demo
//!
//! This example demonstrates the task scheduler rule base and shows how
//! streaming modes work with the CLIPS provider:
//!
//! - StreamMode::Default - Single chunk with all results
//! - StreamMode::Fact - One chunk per derived fact
//! - StreamMode::Rule - One chunk per rule firing
//!
//! Facts are loaded from JSON files in the data/ directory.
//!
//! Run with: cargo run --bin scheduler

use nxuskit::{ChatRequest, Message, NxuskitProvider, ProviderConfig, ThinkingMode};
use std::fs;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== Task Scheduler Expert System ===\n");

    // Create CLIPS provider via NxuskitProvider
    let provider = NxuskitProvider::new(ProviderConfig {
        provider_type: "clips".to_string(),
        model: Some("../../../shared/rules".to_string()),
        ..Default::default()
    })?;

    // Load facts from JSON file
    let data_path = Path::new("../../../shared/data/scheduler-scenario.json");
    let mut base_input: serde_json::Value = if data_path.exists() {
        println!("Loading facts from: {}\n", data_path.display());
        serde_json::from_str(&fs::read_to_string(data_path)?)?
    } else {
        println!("Data file not found, using minimal inline facts\n");
        serde_json::json!({
            "facts": [
                {
                    "template": "task",
                    "values": {
                        "id": "DEMO-001",
                        "name": "Demo Task",
                        "priority": 8,
                        "estimated-hours": 2.0,
                        "status": {"symbol": "pending"},
                        "category": {"symbol": "general"}
                    }
                },
                {
                    "template": "resource",
                    "values": {
                        "id": "RES-001",
                        "name": "Demo Resource",
                        "available-hours": 8.0,
                        "current-load": 0
                    }
                }
            ]
        })
    };

    // =========================================================================
    // Example 1: Non-streaming (default) - single response
    // =========================================================================
    println!("=== Mode 1: Non-Streaming (Full Response) ===\n");

    // Ensure default stream mode
    if let Some(config) = base_input.get_mut("config") {
        if let Some(obj) = config.as_object_mut() {
            obj.insert("stream_mode".to_string(), serde_json::json!("default"));
        }
    }

    let request = ChatRequest::new("task-scheduler.clp")
        .with_message(Message::user(base_input.to_string()))
        .with_thinking_mode(ThinkingMode::Enabled);

    let response = provider.chat(request)?;
    let output: serde_json::Value = serde_json::from_str(&response.content)?;

    // Summarize results
    if let Some(conclusions) = output.get("conclusions").and_then(|c| c.as_array()) {
        let status_updates: Vec<_> = conclusions
            .iter()
            .filter(|f| f.get("template").and_then(|t| t.as_str()) == Some("task-status-update"))
            .collect();
        let exec_orders: Vec<_> = conclusions
            .iter()
            .filter(|f| f.get("template").and_then(|t| t.as_str()) == Some("execution-order"))
            .collect();
        let schedule_entries: Vec<_> = conclusions
            .iter()
            .filter(|f| f.get("template").and_then(|t| t.as_str()) == Some("schedule-entry"))
            .collect();
        let alerts: Vec<_> = conclusions
            .iter()
            .filter(|f| f.get("template").and_then(|t| t.as_str()) == Some("scheduling-alert"))
            .collect();

        println!("Summary:");
        println!("  - Task status updates: {}", status_updates.len());
        println!("  - Execution orders computed: {}", exec_orders.len());
        println!("  - Schedule entries created: {}", schedule_entries.len());
        println!("  - Alerts generated: {}", alerts.len());

        println!("\nTask Status Changes:");
        for update in &status_updates {
            if let Some(values) = update.get("values") {
                println!(
                    "  {} -> {} ({})",
                    values
                        .get("task-id")
                        .and_then(|v| v.as_str())
                        .unwrap_or("?"),
                    values
                        .get("new-status")
                        .and_then(|v| v.get("symbol"))
                        .and_then(|s| s.as_str())
                        .unwrap_or("?"),
                    values.get("reason").and_then(|v| v.as_str()).unwrap_or("")
                );
            }
        }

        println!("\nExecution Order:");
        for order in &exec_orders {
            if let Some(values) = order.get("values") {
                println!(
                    "  [Order {}] {} (priority: {}) - {}",
                    values.get("order").and_then(|v| v.as_i64()).unwrap_or(0),
                    values
                        .get("task-id")
                        .and_then(|v| v.as_str())
                        .unwrap_or("?"),
                    values
                        .get("effective-priority")
                        .and_then(|v| v.as_i64())
                        .unwrap_or(0),
                    values
                        .get("rationale")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                );
            }
        }

        println!("\nSchedule Assignments:");
        for entry in &schedule_entries {
            if let Some(values) = entry.get("values") {
                println!(
                    "  {} -> {} ({})",
                    values
                        .get("task-name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("?"),
                    values
                        .get("resource-name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("?"),
                    values.get("reason").and_then(|v| v.as_str()).unwrap_or("")
                );
            }
        }

        if !alerts.is_empty() {
            println!("\nAlerts:");
            for alert in &alerts {
                if let Some(values) = alert.get("values") {
                    println!(
                        "  [{:?}] {} - {}",
                        values
                            .get("severity")
                            .and_then(|v| v.get("symbol"))
                            .and_then(|s| s.as_str())
                            .unwrap_or("?"),
                        values
                            .get("alert-type")
                            .and_then(|v| v.get("symbol"))
                            .and_then(|s| s.as_str())
                            .unwrap_or("?"),
                        values.get("message").and_then(|v| v.as_str()).unwrap_or("")
                    );
                }
            }
        }
    }

    // =========================================================================
    // Example 2: Streaming - Fact mode (one chunk per derived fact)
    // =========================================================================
    println!("\n=== Mode 2: Streaming (Fact-per-Chunk) ===\n");

    // Set stream mode to "fact"
    if let Some(config) = base_input.get_mut("config") {
        if let Some(obj) = config.as_object_mut() {
            obj.insert("stream_mode".to_string(), serde_json::json!("fact"));
        }
    }

    let request = ChatRequest::new("task-scheduler.clp")
        .with_message(Message::user(base_input.to_string()))
        .with_thinking_mode(ThinkingMode::Enabled);

    let mut stream = provider.chat_stream(request)?;
    let mut fact_count = 0;

    println!("Streaming facts as they are derived:");
    while let Some(Ok(chunk)) = stream.next_chunk() {
        if !chunk.delta.is_empty() {
            fact_count += 1;
            // Parse the fact
            if let Ok(fact) = serde_json::from_str::<serde_json::Value>(&chunk.delta) {
                let template = fact.get("template").and_then(|t| t.as_str()).unwrap_or("?");
                println!("  Chunk {}: {} fact", fact_count, template);
            } else {
                println!("  Chunk {}: (raw)", fact_count);
            }
        }
    }
    println!("\nStream complete. Total facts: {}", fact_count);

    // =========================================================================
    // Example 3: Streaming - Rule mode (one chunk per rule firing)
    // =========================================================================
    println!("\n=== Mode 3: Streaming (Rule-per-Chunk) ===\n");

    // Set stream mode to "rule"
    if let Some(config) = base_input.get_mut("config") {
        if let Some(obj) = config.as_object_mut() {
            obj.insert("stream_mode".to_string(), serde_json::json!("rule"));
            obj.insert("include_trace".to_string(), serde_json::json!(true));
        }
    }

    let request = ChatRequest::new("task-scheduler.clp")
        .with_message(Message::user(base_input.to_string()))
        .with_thinking_mode(ThinkingMode::Enabled);

    let mut stream = provider.chat_stream(request)?;
    let mut rule_count = 0;

    println!("Streaming rule firings:");
    while let Some(Ok(chunk)) = stream.next_chunk() {
        if !chunk.delta.is_empty() {
            rule_count += 1;
            // Parse the rule chunk
            if let Ok(rule_output) = serde_json::from_str::<serde_json::Value>(&chunk.delta) {
                let rule_name = rule_output
                    .get("rule_name")
                    .and_then(|r| r.as_str())
                    .unwrap_or("?");
                let facts_count = rule_output
                    .get("facts")
                    .and_then(|f| f.as_array())
                    .map(|a| a.len())
                    .unwrap_or(0);
                println!(
                    "  Rule {}: {} (produced {} facts)",
                    rule_count, rule_name, facts_count
                );
            } else {
                println!("  Rule {}: (raw chunk)", rule_count);
            }
        }
    }
    println!("\nStream complete. Rule firings: {}", rule_count);

    println!("\n=== Scheduler Demo Complete ===");

    Ok(())
}
