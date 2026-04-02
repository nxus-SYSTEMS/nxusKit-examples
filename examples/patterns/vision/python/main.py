#!/usr/bin/env python3
"""Example: Vision / Multimodal - nxuskit

## nxusKit Features Demonstrated
- Multimodal message construction (text + images)
- Capability detection (supports_vision, max_images)
- Per-request model override (model= keyword argument)
- Fluent image attachment API (with_image_url, with_image_file)
- Provider-specific image handling abstraction

## Interactive Modes
- `--verbose` or `-v`: Show raw request/response data
- `--step` or `-s`: Pause at each step with explanations

## Why This Pattern Matters
Vision APIs differ significantly between providers (different formats, limits,
detail levels). nxusKit abstracts these differences while exposing provider-
specific options through a consistent interface.

Usage:
    # With Claude
    export ANTHROPIC_API_KEY="your-key-here"
    python main.py claude
    python main.py claude --verbose    # Show request/response details
    python main.py claude --step       # Step through with explanations

    # With OpenAI
    export OPENAI_API_KEY="your-key-here"
    python main.py openai
"""

import os
import sys
import time

# Add shared python module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../shared/python"))

from interactive import InteractiveConfig, StepAction
from nxuskit import LLMError, Message, Provider


def main():
    # Parse interactive mode flags
    config = InteractiveConfig.from_args()

    # Get provider from command line args (filter out flags)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    provider_name = args[0] if args else "claude"

    print(f"Vision Example - Using {provider_name} provider")
    print()

    if provider_name == "claude":
        return run_claude_example(config)
    elif provider_name == "openai":
        return run_openai_example(config)
    else:
        print(f"Unknown provider: {provider_name}. Use 'claude' or 'openai'")
        return 1


def run_claude_example(config: InteractiveConfig):
    """Run vision example with Claude."""
    # Step: Checking API key
    if (
        config.step_pause(
            "Checking for Claude API key...",
            [
                "Reads ANTHROPIC_API_KEY from environment",
                "Claude vision requires claude-3 or newer models",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        return 1

    # Step: Creating provider
    if (
        config.step_pause(
            "Creating Claude provider...",
            [
                "nxusKit: Provider factory creates vision-capable provider",
                "Claude Sonnet and Opus models support vision natively",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    # nxusKit: Provider factory creates vision-capable provider
    provider = Provider.claude(model="claude-haiku-4-5-20251001", api_key=api_key)

    # Step: Checking vision capabilities
    if (
        config.step_pause(
            "Checking for vision-capable models...",
            [
                "nxusKit: Capability detection - query models before making requests",
                "supports_vision() checks if a model can handle image inputs",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    # nxusKit: Capability detection - query models before making requests
    print("Checking for vision-capable models...")
    models = provider.list_models()
    vision_models = [m for m in models if m.supports_vision()]

    if not vision_models:
        print(
            "No vision-capable models reported. Proceeding with claude-haiku-4-5 (supports vision).\n"
        )
    else:
        print(f"Found {len(vision_models)} vision-capable models:")
        for m in vision_models:
            print(f"   - {m.name}")
        print()

    # Step: Single image request
    if (
        config.step_pause(
            "Example 1: Single image from URL...",
            [
                "nxusKit: Fluent API for multimodal messages",
                "with_image_url() chains image attachments to messages",
                "Images are encoded and sent in provider-specific format",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("Example 1: Image from URL")
    print("-" * 40)

    # nxusKit: Fluent API for multimodal messages - chain text and images
    msg = Message.user("What's in this image? Describe it briefly.").with_image_url(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png"
    )

    # Verbose: Show request
    config.print_request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        {
            "messages": [{"role": "user", "content": "[text + image]"}],
            "max_tokens": 300,
        },
    )

    try:
        start = time.time()
        response = provider.chat([msg], max_tokens=300)
        elapsed_ms = int((time.time() - start) * 1000)

        # Verbose: Show response
        config.print_response(200, elapsed_ms, {"content": response.content})

        print(f"Response: {response.content}")
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        print(f"Token usage: {in_tok} input, {out_tok} output")
    except LLMError as e:
        print(f"Error: {e}")

    print()

    # Step: Multiple images
    if (
        config.step_pause(
            "Example 2: Multiple images for comparison...",
            [
                "nxusKit: Chain multiple with_image_url() calls",
                "Models can compare and analyze multiple images",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("Example 2: Multiple images for comparison")
    print("-" * 40)

    # nxusKit: Multiple images supported - chain with_image_url calls
    msg = (
        Message.user("Compare these two logos. What do they have in common?")
        .with_image_url(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png"
        )
        .with_image_url(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/ISO_C%2B%2B_Logo.svg/800px-ISO_C%2B%2B_Logo.svg.png"
        )
    )

    try:
        start = time.time()
        response = provider.chat([msg], max_tokens=300)
        elapsed_ms = int((time.time() - start) * 1000)

        config.print_response(200, elapsed_ms, {"content": response.content})
        print(f"Response: {response.content}")
    except LLMError as e:
        print(f"Error: {e}")

    print()
    return 0


def run_openai_example(config: InteractiveConfig):
    """Run vision example with OpenAI."""
    # Step: Checking API key
    if (
        config.step_pause(
            "Checking for OpenAI API key...",
            [
                "Reads OPENAI_API_KEY from environment",
                "GPT-4o and GPT-4o-mini support vision",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return 1

    # Step: Creating provider
    if (
        config.step_pause(
            "Creating OpenAI provider...",
            [
                "nxusKit: Same pattern for OpenAI",
                "Per-request model= override allows one provider for multiple models",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    # nxusKit: One provider handles multiple models via per-request model= override
    provider = Provider.openai(model="gpt-4o-mini", api_key=api_key)

    # Step: Checking vision capabilities
    if (
        config.step_pause(
            "Checking for vision-capable models...",
            [
                "nxusKit: Capability detection works across providers",
                "OpenAI's model list may not expose all capabilities",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("Checking for vision-capable models...")
    models = provider.list_models()
    vision_models = [m for m in models if m.supports_vision()]

    if not vision_models:
        print("Note: OpenAI model list doesn't expose vision capability metadata.")
        print("Using gpt-4o which supports vision.\n")
    else:
        print(f"Found {len(vision_models)} vision-capable models:")
        for m in vision_models:
            print(f"   - {m.name}")
        print()

    # Step: Single image request
    if (
        config.step_pause(
            "Example 1: Single image from URL...",
            [
                "nxusKit: Same fluent API works for OpenAI",
                "GPT-4o-mini is faster and cheaper for basic vision tasks",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("Example 1: Image from URL (gpt-4o-mini)")
    print("-" * 40)

    # nxusKit: Same fluent API works for OpenAI
    msg = Message.user("What's in this image? Describe it briefly.").with_image_url(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png"
    )

    # Verbose: Show request
    config.print_request(
        "POST",
        "https://api.openai.com/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": "[text + image]"}],
            "model": "gpt-4o-mini",
            "max_tokens": 300,
        },
    )

    try:
        start = time.time()
        response = provider.chat([msg], max_tokens=300)
        elapsed_ms = int((time.time() - start) * 1000)

        config.print_response(200, elapsed_ms, {"content": response.content})
        print(f"Response: {response.content}")
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        print(f"Token usage: {in_tok} input, {out_tok} output")
    except LLMError as e:
        print(f"Error: {e}")

    print()

    # Step: High-detail analysis
    if (
        config.step_pause(
            "Example 2: High-detail analysis with GPT-4o...",
            [
                "nxusKit: Per-request model= override switches to gpt-4o",
                "Same provider, different model — no need to create a second provider",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("Example 2: High-detail analysis (GPT-4o)")
    print("-" * 40)

    msg = Message.user(
        "Analyze this diagram in detail. What elements does it contain?"
    ).with_image_url(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Rust_programming_language_black_logo.svg/800px-Rust_programming_language_black_logo.svg.png"
    )

    try:
        start = time.time()
        # nxusKit: Per-request model override — use gpt-4o for detailed analysis
        response = provider.chat([msg], max_tokens=500, model="gpt-4o")
        elapsed_ms = int((time.time() - start) * 1000)

        config.print_response(200, elapsed_ms, {"content": response.content})
        print(f"Response: {response.content}")
    except LLMError as e:
        print(f"Error: {e}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
