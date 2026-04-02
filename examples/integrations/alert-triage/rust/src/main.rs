//! Alert Triage Example
//!
//! Demonstrates LLM-powered alert triage for observability systems.
//!
//! ## Interactive Modes
//!
//! - `--verbose` or `-v`: Show raw HTTP request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! Environment variables:
//! - `NXUSKIT_VERBOSE=1`: Enable verbose mode
//! - `NXUSKIT_STEP=1`: Enable step mode

use alert_triage::{Alert, triage_alerts};
use nxuskit::builders::OllamaProvider;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    println!("=== Alert Triage Demo ===\n");

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

    // Sample alerts (matching Alertmanager format)
    let alerts = vec![
        Alert {
            alertname: "HighMemoryUsage".into(),
            severity: "warning".into(),
            instance: "web-server-01".into(),
            description: "Memory usage above 85% for 5 minutes".into(),
        },
        Alert {
            alertname: "PodCrashLooping".into(),
            severity: "critical".into(),
            instance: "api-deployment-xyz".into(),
            description: "Pod restarted 5 times in last 10 minutes".into(),
        },
        Alert {
            alertname: "SSLCertExpiring".into(),
            severity: "warning".into(),
            instance: "loadbalancer-prod".into(),
            description: "SSL certificate expires in 7 days".into(),
        },
    ];

    println!("Processing {} alerts...\n", alerts.len());

    if config.step_pause(
        "Sending alerts to LLM for triage...",
        &[
            "Each alert will be analyzed by the LLM",
            "The LLM determines priority, likely cause, and suggested actions",
            "Results are returned as structured data",
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
            "alerts_count": alerts.len(),
            "alerts": alerts.iter().map(|a| &a.alertname).collect::<Vec<_>>()
        }),
    );

    let start = std::time::Instant::now();
    match triage_alerts(&provider, "llama3", &alerts).await {
        Ok(results) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            // Show response in verbose mode
            config.print_response(
                200,
                elapsed_ms,
                &serde_json::json!({
                    "results_count": results.len(),
                    "alerts_processed": results.iter().map(|r| &r.alertname).collect::<Vec<_>>()
                }),
            );

            for result in results {
                println!("=== {} ===", result.alertname);
                println!("Priority: {} (1=highest, 5=lowest)", result.priority);
                println!("Summary: {}", result.summary);
                println!("Likely Cause: {}", result.likely_cause);
                println!("Suggested Actions:");
                for action in &result.suggested_actions {
                    println!("  - {}", action);
                }
                println!();
            }
        }
        Err(e) => {
            println!("Triage failed: {:?}", e);
        }
    }

    Ok(())
}
