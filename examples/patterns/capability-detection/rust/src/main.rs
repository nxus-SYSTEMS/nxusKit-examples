//! Example: Capability-Aware Model Selection
//!
//! ## nxusKit Features Demonstrated
//! - ModelInfo metadata (context_window, size_bytes)
//! - Capability-based model filtering
//! - list_models() discovery across providers
//! - Task-to-model matching patterns
//!
//! ## Interactive Modes
//! - `--verbose` or `-v`: Show raw request/response data
//! - `--step` or `-s`: Pause at each API call with explanations
//!
//! ## Why This Pattern Matters
//! Different models have different capabilities (vision, context size, etc.).
//! nxusKit normalizes model metadata across providers, enabling intelligent
//! model selection based on task requirements rather than hardcoded model names.
//!
//! Usage:
//! ```bash
//! # Check OpenAI models
//! OPENAI_API_KEY=your-key cargo run -- openai
//! OPENAI_API_KEY=your-key cargo run -- openai --verbose    # Show details
//! OPENAI_API_KEY=your-key cargo run -- openai --step       # Step through
//!
//! # Check Claude models
//! ANTHROPIC_API_KEY=your-key cargo run -- claude
//!
//! # Check Ollama models (requires Ollama running locally)
//! cargo run -- ollama
//!
//! # Check Ollama with vision detection (slower, makes /api/show calls)
//! OLLAMA_DETECT_VISION=true cargo run -- ollama
//! ```

use nxuskit::prelude::*;
use nxuskit_examples_interactive::{InteractiveConfig, StepAction};
use std::env;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Parse interactive mode flags (filter out --verbose and --step from args)
    let mut config = InteractiveConfig::from_args();

    // Get provider from command line args (skip flags)
    let args: Vec<String> = env::args().filter(|a| !a.starts_with('-')).collect();
    let provider_name = args.get(1).map(|s| s.as_str()).unwrap_or("openai");

    println!("Capability-Aware Model Selection Demo\n");
    println!("Provider: {}\n", provider_name);

    // Step: Creating provider
    if config.step_pause(
        &format!("Creating {} provider...", provider_name),
        &[
            "nxusKit: Provider-specific builder patterns",
            "API keys read from environment variables",
            "list_models() returns normalized ModelInfo across providers",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Create provider based on argument
    let models = match provider_name {
        "openai" => {
            let api_key = env::var("OPENAI_API_KEY")
                .map_err(|_| "Set OPENAI_API_KEY: export OPENAI_API_KEY=your-key")?;
            let provider = OpenAIProvider::builder().api_key(api_key).build()?;

            // Verbose: Show provider configuration
            if config.verbose {
                println!("[VERBOSE] Provider: OpenAI");
                println!("[VERBOSE] Endpoint: https://api.openai.com/v1/models\n");
            }

            provider.list_models()?
        }
        "claude" => {
            let api_key = env::var("ANTHROPIC_API_KEY")
                .map_err(|_| "Set ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY=your-key")?;
            let provider = ClaudeProvider::builder().api_key(api_key).build()?;

            // Verbose: Show provider configuration
            if config.verbose {
                println!("[VERBOSE] Provider: Anthropic");
                println!("[VERBOSE] Endpoint: https://api.anthropic.com/v1/models\n");
            }

            provider.list_models()?
        }
        "ollama" => {
            let provider = OllamaProvider::builder().build()?;
            println!(
                "Tip: Set OLLAMA_DETECT_VISION=true to enable vision detection via /api/show\n"
            );

            // Verbose: Show provider configuration
            if config.verbose {
                println!("[VERBOSE] Provider: Ollama");
                println!("[VERBOSE] Endpoint: http://localhost:11434/api/tags\n");
            }

            provider.list_models()?
        }
        _ => {
            return Err(format!(
                "Unknown provider: {}. Supported: openai, claude, ollama",
                provider_name
            )
            .into());
        }
    };

    // Verbose: Show model count
    if config.verbose {
        println!("[VERBOSE] Models retrieved: {}\n", models.len());
    }

    // Step: Display models
    if config.step_pause(
        "Displaying all models with capabilities...",
        &[
            "nxusKit: Normalized ModelInfo across all providers",
            "context_window: Maximum context length (if available)",
            "size_bytes: Model file size (if available)",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Display all models with their capabilities
    println!("All Available Models:\n");
    println!("{:<40} {:<15}", "Model", "Context Window");
    println!("{}", "=".repeat(55));

    for model in &models {
        let ctx = model
            .context_window
            .map_or("Unknown".to_string(), |n| format!("{}", n));

        println!("{:<40} {:<15}", model.name, ctx);
    }

    // Step: Filter by context window
    if config.step_pause(
        "Filtering models by context window...",
        &[
            "nxusKit: Filter models by capability - works identically across all providers",
            "context_window indicates maximum token count",
            "Same API regardless of whether using OpenAI, Claude, or Ollama",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // nxusKit: Filter models by context window size
    let large_context_models: Vec<_> = models
        .iter()
        .filter(|m| m.context_window.unwrap_or(0) >= 100_000)
        .collect();

    println!(
        "\n\nLarge Context Models (100K+ tokens): {}\n",
        large_context_models.len()
    );

    if large_context_models.is_empty() {
        println!("   No models with 100K+ context found.");
    } else {
        for model in &large_context_models {
            println!("   [+] {}", model.name);
            if let Some(ctx) = model.context_window {
                println!("      Context window: {} tokens", ctx);
            }
            println!();
        }
    }

    // Step: Task-based selection
    if config.step_pause(
        "Demonstrating task-based model selection...",
        &[
            "Select models based on task requirements",
            "Filter by context_window for long documents",
            "Sort by context size for best fit",
        ],
    ) == StepAction::Quit
    {
        return Ok(());
    }

    // Example: Selecting the best model for a specific task
    println!("\nTask-Based Model Selection Examples:\n");

    // Task 1: Need a model with large context for long documents
    println!("Task 1: Process a long document");
    if let Some(best_model) = models
        .iter()
        .filter(|m| m.context_window.unwrap_or(0) >= 100_000)
        .max_by_key(|m| m.context_window.unwrap_or(0))
    {
        println!("   [+] Recommended: {}", best_model.name);
        println!(
            "      Reason: Largest context window ({} tokens)",
            best_model.context_window.unwrap_or(0)
        );
    } else {
        println!("   [i] No models with 100K+ context found");
    }

    // Task 2: Need a small/fast model for simple queries
    println!("\nTask 2: Simple text generation (small model preferred)");
    if let Some(small_model) = models
        .iter()
        .filter(|m| m.size_bytes.is_some())
        .min_by_key(|m| m.size_bytes.unwrap_or(u64::MAX))
    {
        let size_gb = small_model.size_bytes.unwrap_or(0) as f64 / 1_073_741_824.0;
        println!("   [+] Recommended: {}", small_model.name);
        println!(
            "      Reason: Smallest model ({:.1} GB, faster inference)",
            size_gb
        );
    } else if let Some(first_model) = models.first() {
        println!("   [+] Recommended: {}", first_model.name);
        println!("      Reason: First available model");
    } else {
        println!("   [i] No models available");
    }

    // Task 3: Need the largest/most capable model
    println!("\nTask 3: Complex analysis task");
    if let Some(best_model) = models.iter().max_by_key(|m| m.context_window.unwrap_or(0)) {
        println!("   [+] Recommended: {}", best_model.name);
        println!(
            "      Reason: Largest context window ({} tokens)",
            best_model.context_window.unwrap_or(0)
        );
    } else {
        println!("   [i] No models available");
    }

    // Summary statistics
    println!("\n\nModel Summary:\n");
    let with_context: Vec<_> = models
        .iter()
        .filter(|m| m.context_window.is_some())
        .collect();
    let with_size: Vec<_> = models.iter().filter(|m| m.size_bytes.is_some()).collect();

    println!("   Total models: {}", models.len());
    println!("   Models with context window info: {}", with_context.len());
    println!("   Models with size info: {}", with_size.len());

    // Example code snippet for users
    println!("\n\nExample Code:\n");
    println!("```rust");
    println!("// Filter models by context window");
    println!("let large_models: Vec<_> = models.iter()");
    println!("    .filter(|m| m.context_window.unwrap_or(0) >= 100_000)");
    println!("    .collect();");
    println!();
    println!("// Select model with largest context");
    println!("let best = models.iter()");
    println!("    .max_by_key(|m| m.context_window.unwrap_or(0));");
    println!();
    println!("// List model info");
    println!("for model in models {{");
    println!("    println!(\"{{}} context: {{:?}}\", model.name, model.context_window);");
    println!("}}");
    println!("```");

    Ok(())
}
