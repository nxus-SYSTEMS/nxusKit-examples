//! Example: Multi-Provider
//!
//! ## nxusKit Features Demonstrated
//! - Provider abstraction layer (NxuskitProvider)
//! - Sequential multi-provider request execution
//! - Unified response structure across different providers
//! - Provider-agnostic error handling
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! ## Why This Pattern Matters
//! Running the same prompt across providers enables A/B testing, cost comparison,
//! and fallback strategies. nxusKit's unified interface makes this trivial -
//! all providers return the same ChatResponse type with normalized token usage.
//!
//! Usage:
//! ```bash
//! export ANTHROPIC_API_KEY="your-key-here"
//! export OPENAI_API_KEY="your-key-here"
//! cargo run
//! cargo run -- --verbose    # Show request/response details
//! cargo run -- --step       # Step through with explanations
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::env;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags
    let mut config = InteractiveConfig::from_args();

    println!("=== Multi-Provider Comparison Example ===\n");

    // Step: Setting up providers
    if config.step_pause(
        "Creating multiple LLM providers...",
        &[
            "nxusKit: Each provider uses the same builder pattern",
            "Providers are created independently and can fail gracefully",
            "All providers implement the same AsyncProvider trait",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Each provider uses the same builder pattern
    let claude = create_claude_provider().map_err(|e| format!("{}", e))?;
    let openai = create_openai_provider().map_err(|e| format!("{}", e))?;
    let ollama = create_ollama_provider().map_err(|e| format!("{}", e))?;

    // Create the same request for all providers
    let question = "In one sentence, what makes Rust unique among programming languages?";

    // Step: Building requests
    if config.step_pause(
        "Building identical requests for each provider...",
        &[
            "nxusKit: Request structure is provider-agnostic",
            "Only the model name differs between providers",
            "Same parameters work across all providers",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Request structure is provider-agnostic (only model name differs)
    let claude_request = ChatRequest::new("claude-haiku-4-5-20251001")
        .with_message(Message::user(question))
        .with_temperature(0.5)
        .with_max_tokens(100);

    let openai_request = ChatRequest::new("gpt-4")
        .with_message(Message::user(question))
        .with_temperature(0.5)
        .with_max_tokens(100);

    let ollama_request = ChatRequest::new("llama2")
        .with_message(Message::user(question))
        .with_max_tokens(100);

    // Verbose: Show requests
    config.print_request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        &claude_request,
    );
    config.print_request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        &openai_request,
    );
    config.print_request("POST", "http://localhost:11434/api/chat", &ollama_request);

    println!("Question: {}\n", question);
    println!("{}", "=".repeat(80));

    // Step: Sending concurrent requests
    if config.step_pause(
        "Sending concurrent requests to all providers...",
        &[
            "nxusKit: Unified interface enables easy multi-provider comparison",
            "Each provider request uses the same chat() method",
            "Each request returns the same ChatResponse type",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Unified interface enables easy multi-provider comparison
    let start = std::time::Instant::now();
    let claude_result = claude.chat(claude_request);
    let claude_ms = start.elapsed().as_millis() as u64;

    let start = std::time::Instant::now();
    let openai_result = openai.chat(openai_request);
    let openai_ms = start.elapsed().as_millis() as u64;

    let start = std::time::Instant::now();
    let ollama_result = ollama.chat(ollama_request);
    let ollama_ms = start.elapsed().as_millis() as u64;

    // nxusKit: All providers return Result<ChatResponse, NxuskitError> - same handling code
    match &claude_result {
        Ok(response) => {
            config.print_response(200, claude_ms, response);
            println!("\nClaude ({})", response.model);
            println!("{}", response.content);
            let total =
                response.usage.estimated.prompt_tokens + response.usage.estimated.completion_tokens;
            println!("Tokens: {}", total);
        }
        Err(e) => println!("\nClaude: Error - {}", e),
    }

    match &openai_result {
        Ok(response) => {
            config.print_response(200, openai_ms, response);
            println!("\nOpenAI ({})", response.model);
            println!("{}", response.content);
            let total =
                response.usage.estimated.prompt_tokens + response.usage.estimated.completion_tokens;
            println!("Tokens: {}", total);
        }
        Err(e) => println!("\nOpenAI: Error - {}", e),
    }

    match &ollama_result {
        Ok(response) => {
            config.print_response(200, ollama_ms, response);
            println!("\nOllama ({})", response.model);
            println!("{}", response.content);
            let total =
                response.usage.estimated.prompt_tokens + response.usage.estimated.completion_tokens;
            println!("Tokens: {}", total);
        }
        Err(e) => println!("\nOllama: Error - {}", e),
    }

    println!("\n{}", "=".repeat(80));

    Ok(())
}

// nxusKit: Provider creation uses consistent builder pattern
fn create_claude_provider() -> Result<NxuskitProvider, Box<dyn std::error::Error>> {
    let api_key =
        env::var("ANTHROPIC_API_KEY").map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;
    Ok(ClaudeProvider::builder().api_key(api_key).build()?)
}

fn create_openai_provider() -> Result<NxuskitProvider, Box<dyn std::error::Error>> {
    let api_key =
        env::var("OPENAI_API_KEY").map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;
    Ok(OpenAIProvider::builder().api_key(api_key).build()?)
}

fn create_ollama_provider() -> Result<NxuskitProvider, Box<dyn std::error::Error>> {
    Ok(OllamaProvider::builder().build()?)
}
