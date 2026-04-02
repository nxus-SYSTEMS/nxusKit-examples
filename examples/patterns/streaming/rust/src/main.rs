//! Example: Streaming Chat
//!
//! ## nxusKit Features Demonstrated
//! - Unified streaming interface across all providers
//! - Async stream with backpressure support (futures::Stream)
//! - Structured chunk types with delta content and metadata
//! - Final chunk detection with accumulated token usage
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw SSE chunks as they arrive
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! ## Why This Pattern Matters
//! Streaming enables real-time response display, reducing perceived latency.
//! nxusKit normalizes the different streaming formats from Claude, OpenAI,
//! and Ollama into a consistent async Stream interface.
//!
//! Usage:
//! ```bash
//! export ANTHROPIC_API_KEY="your-key-here"
//! cargo run
//! cargo run -- --verbose    # Show SSE chunks
//! cargo run -- --step       # Step through with explanations
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::env;
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags
    let mut config = InteractiveConfig::from_args();

    println!("=== Streaming Chat Example ===\n");

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
            "nxusKit: Same builder pattern as non-streaming",
            "Streaming is just a method call difference on the provider",
            "No HTTP connection is made yet - that happens on first request",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Same builder pattern as non-streaming - streaming is just a method call difference
    let provider = ClaudeProvider::builder()
        .api_key(api_key)
        .model("claude-haiku-4-5-20251001")
        .build()?;

    // Step: Building request
    if config.step_pause(
        "Building chat request...",
        &[
            "nxusKit: Same request type works for both streaming and non-streaming",
            "The provider determines how to handle the request",
            "Streaming adds a 'stream: true' parameter automatically",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Same request type works for both streaming and non-streaming
    let request = ChatRequest::new("claude-haiku-4-5-20251001")
        .with_message(Message::user("Write a short poem about Rust programming"))
        .with_temperature(0.8)
        .with_max_tokens(300);

    // Verbose: Show the request
    config.print_request("POST", "https://api.anthropic.com/v1/messages", &request);

    // Step: Starting stream
    if config.step_pause(
        "Starting streaming request...",
        &[
            "nxusKit: Unified streaming API - returns impl Stream<Item = Result<StreamChunk>>",
            "Server-Sent Events (SSE) arrive as they're generated",
            "Backpressure is handled automatically by the async runtime",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Unified streaming API - returns StreamReceiver implementing futures::Stream
    println!("Streaming response:\n");
    let start = Instant::now();
    let mut stream = provider.chat_stream(request)?;

    let mut chunk_count: usize = 0;

    // nxusKit: Blocking stream processing via Iterator
    for chunk_result in &mut stream {
        match chunk_result {
            Ok(chunk) => {
                chunk_count += 1;

                // Verbose: Show each SSE chunk
                if !chunk.delta.is_empty() {
                    config.print_stream_chunk(chunk_count, &chunk.delta);
                }

                // nxusKit: Normalized chunk structure - delta contains new text
                if !chunk.delta.is_empty() {
                    print!("{}", chunk.delta);
                    use std::io::Write;
                    std::io::stdout().flush()?;
                }
            }
            Err(e) => {
                eprintln!("\nError: {}", e);
                break;
            }
        }
    }

    println!("\n");

    let elapsed_ms = start.elapsed().as_millis() as u64;

    // Verbose: Show stream completion summary
    config.print_stream_done(elapsed_ms, chunk_count);

    println!("Streamed {} chunks in {}ms", chunk_count, elapsed_ms);

    Ok(())
}
