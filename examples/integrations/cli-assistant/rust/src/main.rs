//! CLI Assistant Example
//!
//! Converts natural language to shell commands with streaming output.
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
use std::io::{self, Write};

const SYSTEM_PROMPT: &str = r#"You are a CLI assistant. Convert natural language to shell commands.
Rules:
- Output ONLY the command, no explanation
- Use common Unix commands (ls, grep, find, etc.)
- For dangerous operations, add a comment warning
- If unclear, output a best-guess command with a clarifying comment"#;

/// Generates a shell command from natural language input using streaming.
fn generate_command(
    provider: &NxuskitProvider,
    query: &str,
) -> Result<String, Box<dyn std::error::Error>> {
    let request = ChatRequest::new("llama3")
        .with_message(Message::system(SYSTEM_PROMPT))
        .with_message(Message::user(query));

    let mut stream = provider.chat_stream(request)?;
    let mut output = String::new();

    print!("$ ");
    io::stdout().flush()?;

    while let Some(Ok(chunk)) = stream.next_chunk() {
        print!("{}", chunk.delta);
        io::stdout().flush()?;
        output.push_str(&chunk.delta);
    }
    println!();

    Ok(output)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut config = InteractiveConfig::from_args();

    println!("=== CLI Assistant Demo ===\n");

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

    let queries = vec![
        "find all rust files modified in the last week",
        "show disk usage sorted by size",
        "list all running docker containers",
    ];

    for query in queries {
        println!("Query: \"{}\"", query);

        if config.step_pause(
            "Sending query to LLM...",
            &[
                "The LLM will convert natural language to shell command",
                "Uses streaming to show output as it's generated",
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
                "query": query,
                "stream": true
            }),
        );

        let start = std::time::Instant::now();
        match generate_command(&provider, query) {
            Ok(output) => {
                let elapsed_ms = start.elapsed().as_millis() as u64;
                config.print_response(200, elapsed_ms, &serde_json::json!({ "command": output }));
            }
            Err(e) => println!("Error: {}", e),
        }
        println!();
    }

    // Interactive mode hint
    println!("Tip: For interactive use, pass your query as a command-line argument:");
    println!("  cargo run -- \"your natural language query here\"");

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_system_prompt_is_non_empty() {
        assert!(!SYSTEM_PROMPT.is_empty());
        assert!(SYSTEM_PROMPT.contains("CLI assistant"));
    }
}
