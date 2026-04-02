//! Example: Multi-Provider Fallback
//!
//! ## nxusKit Features Demonstrated
//! - Provider failover chains (Box<dyn AsyncProvider>)
//! - Unified error handling across providers
//! - Resilient request handling with automatic retry
//! - Provider-agnostic fallback logic
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! ## Why This Pattern Matters
//! Production systems need resilience. nxusKit's trait-based design enables
//! easy construction of fallback chains - if one provider fails, the request
//! automatically routes to the next available provider.
//!
//! Usage:
//! ```bash
//! cargo run
//! cargo run -- --verbose    # Show request/response details
//! cargo run -- --step       # Step through with explanations
//! ```
//!
//! Demonstrates automatic failover between LLM providers.

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use retry_fallback::chat_with_fallback;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags
    let mut config = InteractiveConfig::from_args();

    println!("=== Multi-Provider Fallback Demo ===\n");

    // Step: Creating providers
    if config.step_pause(
        "Creating multiple provider instances...",
        &[
            "nxusKit: Each provider uses the same builder pattern",
            "In production, you might use different providers (OpenAI, Claude, Ollama)",
            "Here we use three Ollama instances for demonstration",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Create multiple provider instances
    // In production, you might use different providers (OpenAI, Claude, Ollama)
    let provider1 = OllamaProvider::builder()
        .base_url("http://localhost:11434")
        .build()?;

    let provider2 = OllamaProvider::builder()
        .base_url("http://localhost:11434")
        .build()?;

    let provider3 = OllamaProvider::builder()
        .base_url("http://localhost:11434")
        .build()?;

    // Step: Building provider chain
    if config.step_pause(
        "Building fallback chain with trait objects...",
        &[
            "nxusKit: Trait objects enable heterogeneous provider collections",
            "All providers implement AsyncProvider trait",
            "Box<dyn AsyncProvider> allows mixing different provider types",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Trait objects enable heterogeneous provider collections
    let providers: Vec<Box<dyn AsyncProvider>> = vec![
        Box::new(provider1),
        Box::new(provider2),
        Box::new(provider3),
    ];

    // Step: Creating request
    if config.step_pause(
        "Creating chat request...",
        &[
            "nxusKit: Same request works with any provider in the chain",
            "Request is provider-agnostic - only model name differs",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Create a simple request
    let request =
        ChatRequest::new("llama3").with_message(Message::user("What is 2 + 2? Answer briefly."));

    // Verbose: Show the request
    config.print_request("POST", "http://localhost:11434/api/chat", &request);

    // Step: Executing with fallback
    if config.step_pause(
        "Sending request with fallback chain...",
        &[
            "nxusKit: chat_with_fallback tries providers in order until one succeeds",
            "If provider 1 fails, it automatically tries provider 2, then 3",
            "All failures are logged, only the final error is returned if all fail",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("Sending request with 3-provider fallback chain...\n");

    // nxusKit: chat_with_fallback tries providers in order until one succeeds
    let start = std::time::Instant::now();
    match chat_with_fallback(&providers, &request).await {
        Ok(response) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            config.print_response(200, elapsed_ms, &response);
            println!("\n=== Success ===");
            println!("Response: {}", response.content);
        }
        Err(e) => {
            println!("\n=== All Providers Failed ===");
            println!("Error: {}", e);
        }
    }

    Ok(())
}
