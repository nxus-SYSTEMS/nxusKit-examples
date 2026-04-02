//! Debug script to test raw Ollama streaming
//!
//! This directly tests the HTTP streaming without our provider layer.
//!
//! ## Interactive Modes
//!
//! - `--verbose` or `-v`: Show raw HTTP request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! Environment variables:
//! - `NXUSKIT_VERBOSE=1`: Enable verbose mode
//! - `NXUSKIT_STEP=1`: Enable step mode

use futures::StreamExt;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use reqwest::Client;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    println!("=== Raw Ollama Stream Debug ===\n");

    if config.step_pause(
        "Creating HTTP client...",
        &[
            "This tests raw Ollama streaming without the provider layer",
            "Useful for debugging low-level streaming issues",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let client = Client::new();

    let payload = serde_json::json!({
        "model": "qwen3-vl:2b",
        "messages": [{"role": "user", "content": "Say hello in one sentence."}],
        "stream": true
    });

    if config.step_pause(
        "Sending streaming request to Ollama...",
        &[
            "POST to http://localhost:11434/api/chat",
            "Stream mode enabled - will receive chunks",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Show request in verbose mode
    config.print_request("POST", "http://localhost:11434/api/chat", &payload);

    let stream_start = std::time::Instant::now();
    let response = client
        .post("http://localhost:11434/api/chat")
        .json(&payload)
        .send()
        .await?;

    println!("Status: {}", response.status());

    let mut stream = response.bytes_stream();
    let mut buffer = String::new();
    let mut total_bytes = 0;
    let mut chunk_count = 0;
    let mut lines_parsed = 0;
    let mut thinking_count = 0;
    let mut content_count = 0;
    let mut response_content = String::new();

    while let Some(result) = stream.next().await {
        let bytes = result?;
        total_bytes += bytes.len();
        chunk_count += 1;

        let text = String::from_utf8_lossy(&bytes);
        buffer.push_str(&text);

        // Process complete lines
        while let Some(pos) = buffer.find('\n') {
            let line = buffer[..pos].to_string();
            buffer = buffer[pos + 1..].to_string();

            if line.trim().is_empty() {
                continue;
            }

            lines_parsed += 1;

            // Parse as JSON
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line)
                && let Some(message) = json.get("message")
            {
                let content = message
                    .get("content")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                let thinking = message.get("thinking").and_then(|v| v.as_str());
                let done = json.get("done").and_then(|v| v.as_bool()).unwrap_or(false);

                if !content.is_empty() {
                    content_count += 1;
                    response_content.push_str(content);
                    println!("  Line {}: CONTENT: {:?}", lines_parsed, content);
                }
                if let Some(t) = thinking
                    && !t.is_empty()
                {
                    thinking_count += 1;
                    if thinking_count <= 3 || done {
                        println!("  Line {}: thinking: {:?}", lines_parsed, t);
                    }
                }
                if done {
                    println!("  Line {}: DONE", lines_parsed);
                }
            }
        }
    }

    println!("\n=== Summary ===");
    println!("Total network chunks: {}", chunk_count);
    println!("Total bytes: {}", total_bytes);
    println!("Lines parsed: {}", lines_parsed);
    println!("Thinking chunks: {}", thinking_count);
    println!("Content chunks: {}", content_count);
    println!("Response: {:?}", response_content);

    // Show summary in verbose mode
    let stream_elapsed_ms = stream_start.elapsed().as_millis() as u64;
    config.print_response(
        200,
        stream_elapsed_ms,
        &serde_json::json!({
            "chunks": chunk_count,
            "bytes": total_bytes,
            "lines_parsed": lines_parsed,
            "thinking_chunks": thinking_count,
            "content_chunks": content_count
        }),
    );

    Ok(())
}
