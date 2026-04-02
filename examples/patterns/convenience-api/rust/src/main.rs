//! Example: Convenience API (LiteLLM-style)
//!
//! ## nxusKit Features Demonstrated
//! - One-liner completions with automatic provider detection
//! - Model name routing (gpt-4 → OpenAI, claude-* → Anthropic)
//! - Explicit provider prefixes (openai/gpt-4, anthropic/claude-*)
//! - Streaming convenience function
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each API call with explanations
//!
//! ## Why This Pattern Matters
//! For simple use cases, explicit provider setup is overhead. nxusKit's
//! convenience API auto-detects providers from model names and environment
//! variables, providing a "just works" experience for rapid prototyping.
//!
//! Prerequisites:
//! Set one or more of the following environment variables:
//! - `OPENAI_API_KEY` for OpenAI models
//! - `ANTHROPIC_API_KEY` for Claude models
//! - `OLLAMA_BASE_URL` for Ollama (optional, defaults to localhost:11434)
//!
//! Usage:
//! ```bash
//! # With OpenAI
//! export OPENAI_API_KEY="your-key-here"
//! cargo run
//! cargo run -- --verbose    # Show request/response details
//! cargo run -- --step       # Step through with explanations
//!
//! # With Claude
//! export ANTHROPIC_API_KEY="your-key-here"
//! cargo run
//!
//! # With Ollama (no API key needed)
//! cargo run
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags
    let mut config = InteractiveConfig::from_args();

    println!("=== nxusKit Convenience API Examples ===\n");

    // Step: OpenAI provider
    if config.step_pause(
        "Example 1: OpenAI provider...",
        &[
            "nxusKit: Builder pattern with API key from environment",
            "Model name 'gpt-4o' used in the chat request",
            "API key read from OPENAI_API_KEY environment variable",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // ========================================
    // Example 1: Simple completion with OpenAI
    // ========================================
    println!("Example 1: OpenAI provider\n");
    println!("Asking: What is Rust programming language?\n");

    // Verbose: Show what will be used
    if config.verbose {
        println!("[VERBOSE] Model: gpt-4o");
        println!("[VERBOSE] Provider: OpenAI");
        println!("[VERBOSE] Prompt: Explain Rust in one sentence.\n");
    }

    // nxusKit: Create provider and send a simple chat request
    match std::env::var("OPENAI_API_KEY") {
        Ok(api_key) => {
            let provider = OpenAIProvider::builder().api_key(api_key).build()?;
            let request = ChatRequest::new("gpt-4o")
                .with_message(Message::user("Explain Rust in one sentence."));
            match provider.chat(request) {
                Ok(response) => println!("Response: {}\n", response.content),
                Err(e) => println!("OpenAI request failed: {}\n", e),
            }
        }
        Err(_) => {
            println!("OpenAI example skipped (OPENAI_API_KEY not set)\n");
        }
    }

    // Step: Anthropic provider
    if config.step_pause(
        "Example 2: Anthropic provider...",
        &[
            "Use ClaudeProvider::builder() for Anthropic models",
            "API key read from ANTHROPIC_API_KEY environment variable",
            "Same ChatRequest pattern as OpenAI",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // ========================================
    // Example 2: Anthropic/Claude provider
    // ========================================
    println!("Example 2: Anthropic/Claude provider\n");

    // Verbose: Show provider details
    if config.verbose {
        println!("[VERBOSE] Model: claude-haiku-4-5-20251001");
        println!("[VERBOSE] Provider: Anthropic");
        println!("[VERBOSE] Prompt: What makes Rust memory-safe? Answer in one sentence.\n");
    }

    match std::env::var("ANTHROPIC_API_KEY") {
        Ok(api_key) => {
            let provider = ClaudeProvider::builder().api_key(api_key).build()?;
            let request = ChatRequest::new("claude-haiku-4-5-20251001").with_message(
                Message::user("What makes Rust memory-safe? Answer in one sentence."),
            );
            match provider.chat(request) {
                Ok(response) => println!("Response: {}\n", response.content),
                Err(e) => println!("Anthropic request failed: {}\n", e),
            }
        }
        Err(_) => {
            println!("Anthropic example skipped (ANTHROPIC_API_KEY not set)\n");
        }
    }

    // Step: Streaming
    if config.step_pause(
        "Example 3: Streaming response...",
        &[
            "chat_stream() returns a StreamReceiver of text chunks",
            "Tokens arrive as they are generated",
            "Same provider can do both chat() and chat_stream()",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // ========================================
    // Example 3: Streaming response
    // ========================================
    println!("Example 3: Streaming response\n");
    println!("Streaming response: ");

    match std::env::var("OPENAI_API_KEY") {
        Ok(api_key) => {
            let provider = OpenAIProvider::builder().api_key(api_key).build()?;
            let request = ChatRequest::new("gpt-4o")
                .with_message(Message::user("Count from 1 to 5 with brief comments."));
            match provider.chat_stream(request) {
                Ok(mut stream) => {
                    use std::io::Write;
                    for chunk_result in &mut stream {
                        match chunk_result {
                            Ok(chunk) => {
                                print!("{}", chunk.delta);
                                std::io::stdout().flush()?;
                            }
                            Err(e) => {
                                eprintln!("\nStream error: {}", e);
                                break;
                            }
                        }
                    }
                    println!("\n");
                }
                Err(e) => println!("Streaming setup failed: {}\n", e),
            }
        }
        Err(_) => {
            println!("Streaming example skipped (OPENAI_API_KEY not set)\n");
        }
    }

    // Step: Ollama
    if config.step_pause(
        "Example 4: Ollama local model...",
        &[
            "OllamaProvider requires no API key",
            "Connects to local Ollama instance",
            "Ollama must be running on localhost:11434",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // ========================================
    // Example 4: Ollama (local model)
    // ========================================
    println!("Example 4: Ollama local model\n");

    // Verbose: Show Ollama routing
    if config.verbose {
        println!("[VERBOSE] Model: llama2");
        println!("[VERBOSE] Provider: Ollama");
        println!("[VERBOSE] Endpoint: http://localhost:11434\n");
    }

    {
        let provider = OllamaProvider::builder().build()?;
        let request = ChatRequest::new("llama2").with_message(Message::user(
            "What is the capital of France? One word only.",
        ));
        match provider.chat(request) {
            Ok(response) => println!("Response: {}\n", response.content),
            Err(e) => {
                println!(
                    "Ollama example failed (this is OK if Ollama not running): {}\n",
                    e
                );
                println!("   To use Ollama:");
                println!("   1. Install from https://ollama.ai");
                println!("   2. Run: ollama pull llama2");
                println!("   3. Ollama starts automatically\n");
            }
        }
    }

    // ========================================
    // Example 5: Provider usage patterns
    // ========================================
    println!("Example 5: Provider usage patterns\n");

    println!("nxusKit provider builder pattern:");
    println!("  - OpenAIProvider::builder().api_key(key).build()?");
    println!("  - ClaudeProvider::builder().api_key(key).build()?");
    println!("  - OllamaProvider::builder().build()?");
    println!("  - LmStudioProvider::builder().build()?\n");

    println!("All providers share the same NxuskitProvider API:");
    println!("  - provider.chat(request)?");
    println!("  - provider.chat_stream(request)?");
    println!("  - provider.list_models()?\n");

    // ========================================
    // Summary
    // ========================================
    println!("=== Summary ===");
    println!("\nThe nxusKit API provides:");
    println!("  - Unified builder pattern across all providers");
    println!("  - Automatic credential detection from environment");
    println!("  - Simple streaming with StreamReceiver");
    println!("  - Unified NxuskitProvider API across all providers");
    println!("  - Minimal boilerplate with sensible defaults");
    println!("\nFor more control, use provider-specific builder options.");
    println!("See examples: basic_chat, streaming, multi_provider\n");

    Ok(())
}
