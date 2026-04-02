//! Example: Basic Chat
//!
//! ## nxusKit Features Demonstrated
//! - Unified provider interface (NxuskitProvider)
//! - Type-safe builder pattern with compile-time validation
//! - Consistent error handling with NxuskitError
//! - Normalized token tracking across all providers
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each API call with explanations
//!
//! ## Why This Pattern Matters
//! This is the foundational pattern for all LLM interactions. nxusKit provides
//! a consistent API across providers (Claude, OpenAI, Ollama) so you can switch
//! providers without changing your application code.
//!
//! Usage:
//! ```bash
//! export ANTHROPIC_API_KEY="your-key-here"
//! cargo run
//! cargo run -- --verbose    # Show request/response details
//! cargo run -- --step       # Step through with explanations
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::env;
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags
    let mut config = InteractiveConfig::from_args();

    // Step: Getting API key
    if config.step_pause(
        "Getting API key from environment...",
        &[
            "Reads ANTHROPIC_API_KEY from environment variables",
            "This keeps secrets out of source code",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Get API key from environment
    let api_key = env::var("ANTHROPIC_API_KEY")
        .map_err(|_| "Set ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY=your-key")?;

    // Step: Creating provider
    if config.step_pause(
        "Creating Claude provider...",
        &[
            "nxusKit: Type-safe builder ensures all required fields are set",
            "The builder pattern catches configuration errors at compile time",
            "No HTTP connection is made yet - that happens on first request",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Type-safe builder ensures all required fields are set at compile time
    let provider = ClaudeProvider::builder()
        .api_key(api_key) // Required - compile error if missing
        .model("claude-haiku-4-5-20251001") // Optional - uses default if not set
        .build()?; // Returns Result for graceful error handling

    // Step: Building request
    if config.step_pause(
        "Building chat request...",
        &[
            "nxusKit: Fluent request builder with type-safe message construction",
            "Messages are validated at compile time (system, user, assistant roles)",
            "Parameters like temperature and max_tokens have sensible defaults",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Fluent request builder with type-safe message construction
    let request = ChatRequest::new("claude-haiku-4-5-20251001")
        .with_message(Message::system("You are a helpful programming assistant"))
        .with_message(Message::user("What is Rust and why should I use it?"))
        .with_temperature(0.7)
        .with_max_tokens(500);

    // Verbose: Show the request
    config.print_request("POST", "https://api.anthropic.com/v1/messages", &request);

    // Step: Sending request
    if config.step_pause(
        "Sending request to Claude API...",
        &[
            "nxusKit: Unified interface - same pattern works for all providers",
            "The request is serialized to JSON and sent via HTTPS",
            "Response is parsed and normalized to a common format",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Unified interface - same pattern works for all providers
    println!("Sending request to Claude...\n");
    let start = Instant::now();
    let response = provider.chat(request)?;
    let elapsed_ms = start.elapsed().as_millis() as u64;

    // Verbose: Show the response
    config.print_response(200, elapsed_ms, &response);

    // Display response
    println!("Response:\n{}\n", response.content);
    println!("Model: {}", response.model);

    // nxusKit: Unified token tracking - same format regardless of provider
    println!("Token usage:");
    println!(
        "  Prompt: {} tokens",
        response.usage.estimated.prompt_tokens
    );
    println!(
        "  Completion: {} tokens",
        response.usage.estimated.completion_tokens
    );
    let total = response.usage.estimated.prompt_tokens + response.usage.estimated.completion_tokens;
    println!("  Total: {} tokens", total);

    Ok(())
}
