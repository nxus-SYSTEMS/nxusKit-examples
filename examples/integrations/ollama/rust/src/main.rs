//! Example: Ollama Local LLM Integration
//!
//! Demonstrates using nxusKit with Ollama for local LLM inference.
//!
//! Prerequisites:
//!   - Ollama installed and running (`ollama serve`)
//!   - A model pulled (e.g., `ollama pull llama3`)
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! Usage:
//! ```bash
//! cargo run
//! cargo run -- --verbose
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    if config.step_pause(
        "Creating Ollama provider...",
        &[
            "Connects to local Ollama server (localhost:11434)",
            "Ollama runs open-source LLMs locally — no API key needed",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Create Ollama provider — connects to local server
    let provider = OllamaProvider::builder().build()?;

    // Check server connectivity
    if config.step_pause(
        "Checking Ollama server...",
        &[
            "Pings the Ollama server to verify it's running",
            "Returns an error if Ollama is not available",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("[OK] Connected to Ollama\n");

    // List available models
    if config.step_pause(
        "Listing available models...",
        &[
            "Lists all models pulled to the local Ollama instance",
            "Models are downloaded with: ollama pull <model>",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("Available models:");
    let models = provider.list_models()?;
    if models.is_empty() {
        println!("  (no models found — run: ollama pull llama3)");
        return Ok(());
    }
    for model in models.iter().take(10) {
        println!("  - {}", model.name);
    }
    if models.len() > 10 {
        println!("  ... and {} more", models.len() - 10);
    }
    println!();

    // Pick a model — prefer llama3 if available
    let model = models
        .iter()
        .find(|m| m.name.starts_with("llama3"))
        .or_else(|| models.first())
        .map(|m| m.name.clone())
        .unwrap_or_else(|| "llama3".to_string());

    println!("Using model: {}\n", model);

    // Basic chat
    if config.step_pause(
        "Sending a chat request...",
        &[
            "nxusKit: Same ChatRequest API works for Ollama as for Claude/OpenAI",
            "The request is sent to the local Ollama server",
            "Response is streamed back and collected",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("Chat: \"What is Rust in one sentence?\"");
    let request = ChatRequest::new(&model)
        .with_message(Message::user("What is Rust? Answer in one sentence."))
        .with_max_tokens(100);

    config.print_request("POST", "http://localhost:11434/api/chat", &request);

    let start = std::time::Instant::now();
    let response = provider.chat(request)?;
    let elapsed_ms = start.elapsed().as_millis() as u64;

    config.print_response(200, elapsed_ms, &response);
    println!("Response: {}", response.content);
    println!(
        "Tokens: {} input, {} output\n",
        response.usage.estimated.prompt_tokens, response.usage.estimated.completion_tokens
    );

    println!("=== Ollama Example Complete ===");
    Ok(())
}
