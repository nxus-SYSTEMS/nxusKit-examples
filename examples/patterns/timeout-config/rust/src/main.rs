//! Example: Timeout Configuration
//!
//! ## nxusKit Features Demonstrated
//! - Granular timeout settings (connection, stream_read, total)
//! - Default timeout values for different provider types
//! - Builder pattern with optional timeout overrides
//! - Provider-specific timeout recommendations
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each API call with explanations
//!
//! ## Why This Pattern Matters
//! Network conditions and response times vary. nxusKit provides sensible defaults
//! while allowing fine-grained timeout control for different scenarios (quick
//! connection failure detection vs. long-running streaming requests).
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
use std::time::{Duration, Instant};

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

    println!("=== Timeout Configuration Examples ===\n");

    // Step: Default timeouts
    if config.step_pause(
        "Example 1: Using default timeouts...",
        &[
            "nxusKit provides sensible default timeout values",
            "Connection: 60s, Stream read: 120s, Total: 60s",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Example 1: Using default timeouts
    println!("1. Using default timeouts:");
    let _provider_defaults = ClaudeProvider::builder()
        .api_key(&api_key)
        .model("claude-3-5-haiku-20241022")
        .build()?;
    println!("   Connection timeout: 60s");
    println!("   Stream read timeout: 120s");
    println!("   Total timeout: 60s\n");

    // Verbose: Show default configuration
    if config.verbose {
        println!("[VERBOSE] Default timeout configuration:");
        println!("[VERBOSE]   connection_timeout: 60s");
        println!("[VERBOSE]   stream_read_timeout: 120s");
        println!("[VERBOSE]   total_timeout: 60s\n");
    }

    // Step: General timeout
    if config.step_pause(
        "Example 2: Using timeout_ms builder method...",
        &[
            "timeout_ms() sets the request timeout in milliseconds",
            "Accepts a u64 value for milliseconds",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Example 2: Using general timeout (backward compatible)
    println!("2. Using general timeout:");
    let _provider_general = ClaudeProvider::builder()
        .api_key(&api_key)
        .model("claude-3-5-haiku-20241022")
        .timeout_ms(Duration::from_secs(30).as_millis() as u64)
        .build()?;
    println!("   Timeout set to: 30s (30000ms)\n");

    // Step: Granular timeouts
    if config.step_pause(
        "Example 3: Using a longer timeout for streaming...",
        &[
            "nxusKit: timeout_ms sets the overall request timeout",
            "Use a longer timeout for streaming or complex requests",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Set timeout via timeout_ms builder method
    println!("3. Using a longer timeout for streaming:");
    let provider_granular = ClaudeProvider::builder()
        .api_key(&api_key)
        .model("claude-3-5-haiku-20241022")
        .timeout_ms(Duration::from_secs(120).as_millis() as u64) // 120s timeout
        .build()?;
    println!("   Timeout: 120s (suitable for longer responses)\n");

    // Verbose: Show timeout configuration
    if config.verbose {
        println!("[VERBOSE] Timeout configuration:");
        println!("[VERBOSE]   timeout_ms: 120000 (120s)\n");
    }

    // Example 4: Using a shorter timeout for quick responses
    println!("4. Using a short timeout for quick queries:");
    let _provider_short = ClaudeProvider::builder()
        .api_key(&api_key)
        .model("claude-3-5-haiku-20241022")
        .timeout_ms(Duration::from_secs(15).as_millis() as u64) // 15s timeout
        .build()?;
    println!("   Timeout: 15s (suitable for quick queries)\n");

    // Step: Testing with real request
    if config.step_pause(
        "Example 5: Testing with a real request...",
        &[
            "Making an actual API call to Claude",
            "Uses the granular timeout configuration",
            "Demonstrates timeout settings in action",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Example 5: Test with a real request
    println!("5. Testing with a real request:");
    println!("   Using provider with granular timeouts...");

    let request = ChatRequest::new("claude-3-5-haiku-20241022")
        .with_message(Message::user("What is Rust in one sentence?"))
        .with_max_tokens(100);

    // Verbose: Show the request
    config.print_request("POST", "https://api.anthropic.com/v1/messages", &request);

    let start = Instant::now();
    match provider_granular.chat(request) {
        Ok(response) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;

            // Verbose: Show the response
            config.print_response(200, elapsed_ms, &response);

            println!("   Request succeeded!");
            println!("   Response: {}", response.content);
            let total =
                response.usage.estimated.prompt_tokens + response.usage.estimated.completion_tokens;
            println!("   Tokens used: {}", total);
        }
        Err(e) => {
            println!("   Request failed: {}", e);
        }
    }

    println!("\n=== Configuration Best Practices ===\n");
    println!("• Use default timeouts for most cases");
    println!("• Set connection_timeout low (5-15s) to detect network issues quickly");
    println!("• Set stream_read_timeout high (180-300s) for long-running streams");
    println!("• Set total_timeout based on your application's needs");
    println!("• For Ollama (local), use longer timeouts (default: 120s-180s)");
    println!("• For Claude/OpenAI (remote), shorter timeouts work well (default: 60s-120s)\n");

    Ok(())
}
