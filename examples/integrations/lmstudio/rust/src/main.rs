//! LM Studio provider example
//!
//! This example demonstrates using the LM Studio provider for local LLM inference.
//! LM Studio provides an OpenAI-compatible API for running models locally.
//!
//! Prerequisites:
//! 1. Install LM Studio from https://lmstudio.ai
//! 2. Download and load a model (e.g., llama-2-7b, mistral-7b)
//! 3. Start the local server (default: http://localhost:1234)
//!
//! Usage:
//! ```bash
//! # With default settings (localhost:1234)
//! cargo run --example lmstudio_example
//!
//! # With custom base URL
//! export LMSTUDIO_BASE_URL="http://localhost:8080/v1"
//! cargo run --example lmstudio_example
//!
//! # With API key (if configured in LM Studio)
//! export LMSTUDIO_API_KEY="your-key-here"
//! cargo run --example lmstudio_example
//! ```
//!
//! ## Interactive Modes
//!
//! - `--verbose` or `-v`: Show raw HTTP request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! Environment variables:
//! - `NXUSKIT_VERBOSE=1`: Enable verbose mode
//! - `NXUSKIT_STEP=1`: Enable step mode

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::env;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    println!("=== LM Studio Provider Example ===\n");

    // Get configuration from environment or use defaults
    let base_url = env::var("LMSTUDIO_BASE_URL").unwrap_or_else(|_| {
        println!("Using default LM Studio URL: http://localhost:1234/v1");
        "http://localhost:1234/v1".to_string()
    });

    if env::var("LMSTUDIO_API_KEY").is_err() {
        println!("No API key configured (this is usually fine for local LM Studio)\n");
    }

    if config.step_pause(
        "Creating LM Studio provider...",
        &[
            "This initializes the HTTP client for LM Studio",
            "Connects to the local LM Studio server",
            "Will discover available models automatically",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Build provider with minimal configuration
    // We'll discover the available models and select one
    let temp_provider = LmStudioProvider::builder().base_url(&base_url).build()?;

    // ========================================
    // 1. Discover available models
    // ========================================
    if config.step_pause(
        "Discovering available models...",
        &[
            "Queries the LM Studio API to list loaded models",
            "Checks for vision-capable models automatically",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("Discovering available models...");
    match temp_provider.list_models() {
        Ok(models) => {
            if models.is_empty() {
                eprintln!("No models found. Make sure LM Studio is running and has models loaded.");
                eprintln!("   Visit https://lmstudio.ai for setup instructions.");
                return Ok(());
            }

            println!("Found {} model(s):\n", models.len());
            for (i, model) in models.iter().enumerate() {
                println!("  {}. {}", i + 1, model.name);
                if let Some(size) = model.size_bytes {
                    let size_gb = size as f64 / 1_073_741_824.0;
                    println!("     Size: {:.1} GB", size_gb);
                }
                if let Some(ctx) = model.context_window {
                    println!("     Max context: {} tokens", ctx);
                }
                println!();
            }

            // Use the first available model
            let selected_model = &models[0].name;
            println!("Using model: {}\n", selected_model);

            // ========================================
            // 2. Rebuild provider with selected model
            // ========================================
            let provider = LmStudioProvider::builder().base_url(&base_url).build()?;

            // ========================================
            // 3. Basic chat completion
            // ========================================
            if config.step_pause(
                "Sending basic chat request...",
                &[
                    "Creates a ChatRequest with system and user messages",
                    "Sets temperature and max_tokens parameters",
                ],
            ) == StepAction::Quit
            {
                return Ok(());
            }

            println!("Sending basic chat request...\n");

            let request = ChatRequest::new(selected_model)
                .with_message(Message::system(
                    "You are a helpful AI assistant running locally via LM Studio.",
                ))
                .with_message(Message::user(
                    "In one short paragraph, explain what LM Studio is and why someone might use it.",
                ))
                .with_temperature(0.7)
                .with_max_tokens(200);

            // Show request in verbose mode
            config.print_request(
                "POST",
                &format!("{}/chat/completions", base_url),
                &serde_json::json!({
                    "model": selected_model,
                    "messages": ["system: AI assistant...", "user: Explain LM Studio..."],
                    "temperature": 0.7,
                    "max_tokens": 200
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
                            "model": &response.model,
                            "content_length": response.content.len(),
                            "prompt_tokens": response.usage.estimated.prompt_tokens,
                            "completion_tokens": response.usage.estimated.completion_tokens
                        }),
                    );

                    println!("Response:\n{}\n", response.content);
                    println!("Model: {}", response.model);
                    println!("Token usage:");
                    println!(
                        "  Prompt: {} tokens",
                        response.usage.estimated.prompt_tokens
                    );
                    println!(
                        "  Completion: {} tokens",
                        response.usage.estimated.completion_tokens
                    );
                    let total = response.usage.estimated.prompt_tokens
                        + response.usage.estimated.completion_tokens;
                    println!("  Total: {} tokens\n", total);
                }
                Err(e) => {
                    eprintln!("Chat request failed: {}", e);
                    eprintln!("   Make sure the model is loaded in LM Studio.");
                    return Ok(());
                }
            }

            // ========================================
            // 4. Streaming chat completion
            // ========================================
            if config.step_pause(
                "Demonstrating streaming response...",
                &[
                    "Uses chat_stream() for real-time token output",
                    "Tokens appear as they are generated",
                ],
            ) == StepAction::Quit
            {
                return Ok(());
            }

            println!("Demonstrating streaming response...\n");

            let stream_request = ChatRequest::new(selected_model)
                .with_message(Message::user(
                    "Count from 1 to 5, with a brief comment about each number.",
                ))
                .with_temperature(0.8)
                .with_max_tokens(300);

            match provider.chat_stream(stream_request) {
                Ok(mut stream) => {
                    print!("Streaming: ");
                    use std::io::Write;

                    for chunk_result in &mut stream {
                        match chunk_result {
                            Ok(chunk) => {
                                if !chunk.delta.is_empty() {
                                    print!("{}", chunk.delta);
                                    std::io::stdout().flush()?;
                                }
                            }
                            Err(e) => {
                                eprintln!("\nStream error: {}", e);
                                break;
                            }
                        }
                    }

                    println!("\n");
                }
                Err(e) => {
                    eprintln!("Streaming request failed: {}", e);
                }
            }

            // ========================================
            // 5. Model info summary
            // ========================================
            if config.step_pause(
                "Showing model info summary...",
                &[
                    "ModelInfo provides normalized metadata across providers",
                    "Available fields: name, context_window, size_bytes",
                ],
            ) == StepAction::Quit
            {
                return Ok(());
            }

            println!("Model info for '{}':", selected_model);
            if let Some(model_info) = models.iter().find(|m| m.name == *selected_model) {
                if let Some(ctx) = model_info.context_window {
                    println!("  Context window: {} tokens", ctx);
                }
                if let Some(size) = model_info.size_bytes {
                    let size_gb = size as f64 / 1_073_741_824.0;
                    println!("  Size: {:.1} GB", size_gb);
                }
            }

            println!("\n=== Example completed successfully! ===");
        }
        Err(e) => {
            eprintln!("Failed to connect to LM Studio: {}", e);
            eprintln!("\nTroubleshooting:");
            eprintln!("  1. Is LM Studio running?");
            eprintln!("  2. Is the local server started? (Check LM Studio's 'Local Server' tab)");
            eprintln!("  3. Is the server URL correct? (Default: http://localhost:1234)");
            eprintln!("  4. Do you have any models loaded?");
            eprintln!("\nFor setup help, visit: https://lmstudio.ai/docs");
        }
    }

    Ok(())
}
