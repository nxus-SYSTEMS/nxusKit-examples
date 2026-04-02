//! Example: Vision / Multimodal
//!
//! ## nxusKit Features Demonstrated
//! - Multimodal message construction (text + images)
//! - Capability detection (supports_vision, max_images)
//! - Provider-specific image handling abstraction
//! - URL-based image support with detail level options
//! - Multiple image comparison in a single request
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each step with explanations
//!
//! ## Why This Pattern Matters
//! Vision APIs differ significantly between providers (different formats, limits,
//! detail levels). nxusKit abstracts these differences while exposing provider-
//! specific options (like OpenAI's detail level) through a consistent interface.
//!
//! # Running the example
//!
//! ```bash
//! # With Claude
//! ANTHROPIC_API_KEY=your_key cargo run -- claude
//!
//! # With OpenAI
//! OPENAI_API_KEY=your_key cargo run -- openai
//!
//! # With verbose output
//! cargo run -- claude --verbose
//!
//! # Step-by-step mode
//! cargo run -- openai --step
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::env;
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags
    let mut config = InteractiveConfig::from_args();

    // Get provider from command line args (excluding flags)
    let args: Vec<String> = env::args()
        .skip(1)
        .filter(|a| !a.starts_with('-'))
        .collect();
    let provider_name = args.first().map(|s| s.as_str()).unwrap_or("claude");

    println!("Vision Example - Using {} provider\n", provider_name);

    match provider_name {
        "claude" => run_claude_example(&mut config)?,
        "openai" => run_openai_example(&mut config)?,
        other => {
            return Err(format!("Unknown provider: {}. Use 'claude' or 'openai'", other).into());
        }
    }

    Ok(())
}

fn run_claude_example(config: &mut InteractiveConfig) -> Result<(), Box<dyn std::error::Error>> {
    // Step: Getting API key
    if config.step_pause(
        "Checking for Claude API key...",
        &[
            "Reads ANTHROPIC_API_KEY from environment variables",
            "This keeps secrets out of source code",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let api_key = env::var("ANTHROPIC_API_KEY")
        .map_err(|_| "Set ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY=your-key")?;

    // Step: Creating provider
    if config.step_pause(
        "Creating Claude provider...",
        &[
            "nxusKit: Type-safe builder ensures all required fields are set",
            "The builder pattern catches configuration errors at compile time",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let provider = ClaudeProvider::builder().api_key(api_key).build()?;

    // Step: Checking vision capabilities
    if config.step_pause(
        "Checking for vision-capable models...",
        &[
            "nxusKit: Capability detection - query models before making requests",
            "supports_vision() checks if a model can handle image inputs",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Capability detection - query models before making requests
    println!("Checking for vision-capable models...");
    let models = provider.list_models()?;
    let vision_models: Vec<_> = models.iter().filter(|m| m.supports_vision()).collect();

    if vision_models.is_empty() {
        println!(
            "No vision-capable models reported. Proceeding with claude-haiku-4-5 (supports vision).\n"
        );
    } else {
        println!("Found {} vision-capable models:", vision_models.len());
        for model in &vision_models {
            println!("   - {}", model.name);
        }
        println!();
    }

    // Example 1: Image from URL
    println!("Example 1: Image from URL");
    println!("{}", "-".repeat(40));

    // Step: Building multimodal request
    if config.step_pause(
        "Building multimodal request with image URL...",
        &[
            "nxusKit: Fluent API for multimodal messages - chain text and images",
            "with_image_url() adds an image from a URL to the message",
            "Provider handles fetching and encoding the image",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Fluent API for multimodal messages - chain text and images
    let msg = Message::user("What's in this image? Describe it briefly.")
        .with_image_url("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png");

    let request = ChatRequest::new("claude-haiku-4-5-20251001")
        .with_message(msg)
        .with_max_tokens(300);

    // Verbose: Show the request
    config.print_request("POST", "https://api.anthropic.com/v1/messages", &request);

    // Step: Sending request
    if config.step_pause(
        "Sending vision request to Claude API...",
        &[
            "nxusKit: Same chat() method works for text and multimodal",
            "The request includes the image URL for Claude to process",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let start = Instant::now();
    match provider.chat(request) {
        Ok(response) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            config.print_response(200, elapsed_ms, &response);
            println!("Response: {}\n", response.content);
            println!(
                "Token usage: {} input, {} output\n",
                response.usage.estimated.prompt_tokens, response.usage.estimated.completion_tokens
            );
        }
        Err(e) => eprintln!("Error: {}\n", e),
    }

    // Example 2: Multiple images for comparison
    println!("Example 2: Multiple images for comparison");
    println!("{}", "-".repeat(40));

    // Step: Building multi-image request
    if config.step_pause(
        "Building request with multiple images...",
        &[
            "nxusKit: Chain multiple with_image_url() calls for comparison tasks",
            "Claude can analyze and compare multiple images in one request",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let msg = Message::user("Compare these two logos. What do they have in common?")
        .with_image_url("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png")
        .with_image_url("https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/ISO_C%2B%2B_Logo.svg/800px-ISO_C%2B%2B_Logo.svg.png");

    let request = ChatRequest::new("claude-haiku-4-5-20251001")
        .with_message(msg)
        .with_max_tokens(300);

    // Verbose: Show the request
    config.print_request("POST", "https://api.anthropic.com/v1/messages", &request);

    // Step: Sending multi-image request
    if config.step_pause(
        "Sending multi-image comparison request...",
        &["Claude will analyze both images and find commonalities"],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let start = Instant::now();
    match provider.chat(request) {
        Ok(response) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            config.print_response(200, elapsed_ms, &response);
            println!("Response: {}\n", response.content);
            println!(
                "Token usage: {} input, {} output\n",
                response.usage.estimated.prompt_tokens, response.usage.estimated.completion_tokens
            );
        }
        Err(e) => eprintln!("Error: {}\n", e),
    }

    Ok(())
}

fn run_openai_example(config: &mut InteractiveConfig) -> Result<(), Box<dyn std::error::Error>> {
    // Step: Getting API key
    if config.step_pause(
        "Checking for OpenAI API key...",
        &[
            "Reads OPENAI_API_KEY from environment variables",
            "This keeps secrets out of source code",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let api_key = env::var("OPENAI_API_KEY")
        .map_err(|_| "Set OPENAI_API_KEY: export OPENAI_API_KEY=your-key")?;

    // Step: Creating provider
    if config.step_pause(
        "Creating OpenAI provider...",
        &[
            "nxusKit: Same factory pattern as Claude provider",
            "Provider abstraction hides OpenAI-specific details",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Model specified per-request in ChatRequest — one provider handles multiple models
    // (Python SDK binds model at provider creation; see Python variant)
    let provider = OpenAIProvider::builder().api_key(api_key).build()?;

    // Step: Checking vision capabilities
    if config.step_pause(
        "Checking for vision-capable models...",
        &[
            "nxusKit: Capability detection works across providers",
            "OpenAI's model list may not expose all capabilities",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    println!("Checking for vision-capable models...");
    let models = provider.list_models()?;
    let vision_models: Vec<_> = models.iter().filter(|m| m.supports_vision()).collect();

    if vision_models.is_empty() {
        println!("Note: OpenAI model list doesn't expose vision capability metadata.");
        println!("Using gpt-4o which supports vision.\n");
    } else {
        println!("Found {} vision-capable models:", vision_models.len());
        for model in &vision_models {
            println!("   - {}", model.name);
        }
        println!();
    }

    // Example 1: Image from URL (low detail)
    println!("Example 1: Image from URL (low detail)");
    println!("{}", "-".repeat(40));

    // Step: Building low-detail request
    if config.step_pause(
        "Building request with low detail level...",
        &[
            "nxusKit: with_detail() sets OpenAI's image detail level",
            "'low' is faster and cheaper, uses fewer tokens",
            "Provider-specific options through a consistent interface",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let msg = Message::user("What's in this image? Describe it briefly.")
        .with_image_url("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png")
        .with_detail("low"); // Faster and cheaper

    let request = ChatRequest::new("gpt-4o-mini")
        .with_message(msg)
        .with_max_tokens(300);

    // Verbose: Show the request
    config.print_request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        &request,
    );

    // Step: Sending request
    if config.step_pause(
        "Sending low-detail vision request to OpenAI...",
        &["Using gpt-4o-mini for cost-effective vision tasks"],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let start = Instant::now();
    match provider.chat(request) {
        Ok(response) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            config.print_response(200, elapsed_ms, &response);
            println!("Response: {}\n", response.content);
            println!(
                "Token usage: {} input, {} output\n",
                response.usage.estimated.prompt_tokens, response.usage.estimated.completion_tokens
            );
        }
        Err(e) => eprintln!("Error: {}\n", e),
    }

    // Example 2: High-detail analysis
    println!("Example 2: High-detail analysis");
    println!("{}", "-".repeat(40));

    // Step: Building high-detail request
    if config.step_pause(
        "Building request with high detail level...",
        &[
            "nxusKit: 'high' detail uses more tokens for detailed analysis",
            "OpenAI processes the image at higher resolution",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let msg = Message::user("Analyze this diagram in detail. What elements does it contain?")
        .with_image_url("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png")
        .with_detail("high"); // More detailed analysis

    let request = ChatRequest::new("gpt-4o")
        .with_message(msg)
        .with_max_tokens(500);

    // Verbose: Show the request
    config.print_request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        &request,
    );

    // Step: Sending high-detail request
    if config.step_pause(
        "Sending high-detail vision request to OpenAI...",
        &["Using gpt-4o for more detailed image analysis"],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    let start = Instant::now();
    match provider.chat(request) {
        Ok(response) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            config.print_response(200, elapsed_ms, &response);
            println!("Response: {}\n", response.content);
            println!(
                "Token usage: {} input, {} output\n",
                response.usage.estimated.prompt_tokens, response.usage.estimated.completion_tokens
            );
        }
        Err(e) => eprintln!("Error: {}\n", e),
    }

    Ok(())
}
