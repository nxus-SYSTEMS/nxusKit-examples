#!/usr/bin/env python3
"""Example: Token Budget with Streaming - nxuskit

## nxusKit Features Demonstrated
- stream_with_callback for real-time streaming with a processing hook
- Manual stream iteration for fine-grained control
- Budget-based early cancellation (stop consuming after N tokens)
- StreamChunk fields: delta, usage, finish_reason

## Interactive Modes
- `--verbose` or `-v`: Show raw SSE chunks as they arrive
- `--step` or `-s`: Pause at each step with explanations

## Why This Pattern Matters
Token budgets are essential for cost control. By streaming and counting tokens
as they arrive, you can stop generation early when a budget is exhausted --
paying only for tokens actually consumed rather than the full max_tokens.

Usage:
    export ANTHROPIC_API_KEY="your-key-here"
    python main.py
    python main.py --verbose    # Show SSE chunks
    python main.py --step       # Step through with explanations

Or with Ollama (no API key needed):
    python main.py ollama
"""

import os
import sys
import time
from typing import Tuple

# Add shared python module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../shared/python"))

from interactive import InteractiveConfig, StepAction
from nxuskit import LLMError, Message, Provider, stream_with_callback


class TokenBudget:
    """Tracks estimated token consumption during streaming.

    Uses a rough heuristic: ~4 characters per token (English average).
    For exact counts, use the final chunk's usage field.
    """

    CHARS_PER_TOKEN_ESTIMATE = 4

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.chars_received = 0
        self.chunks_received = 0
        self.exceeded = False

    @property
    def estimated_tokens(self) -> int:
        return self.chars_received // self.CHARS_PER_TOKEN_ESTIMATE

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.estimated_tokens)

    def consume(self, text: str) -> bool:
        """Record consumed text. Returns True if budget is still available."""
        self.chars_received += len(text)
        self.chunks_received += 1
        if self.estimated_tokens >= self.max_tokens:
            self.exceeded = True
            return False
        return True

    def summary(self) -> str:
        status = "EXCEEDED" if self.exceeded else "OK"
        return (
            f"Budget: {self.max_tokens} tokens | "
            f"Estimated used: ~{self.estimated_tokens} | "
            f"Chunks: {self.chunks_received} | "
            f"Status: {status}"
        )


def stream_with_budget(
    provider,
    messages,
    budget: TokenBudget,
    config: InteractiveConfig,
) -> Tuple[str, bool]:
    """Stream a response, stopping early if the token budget is exceeded.

    Returns (collected_text, was_budget_exceeded).
    """
    collected: list[str] = []
    chunk_count = 0

    config.print_request(
        "POST",
        f"https://api.{provider.provider_name}.com/v1/chat",
        {"stream": True, "budget_tokens": budget.max_tokens},
    )

    start = time.time()
    stream = provider.chat_stream(
        messages,
        temperature=0.7,
        max_tokens=800,  # allow model to generate plenty -- we cut client-side
    )

    # nxusKit: Manual iteration gives full control over each chunk
    for chunk in stream:
        chunk_count += 1

        if chunk.delta:
            config.print_stream_chunk(chunk_count, chunk.delta)
            print(chunk.delta, end="", flush=True)
            collected.append(chunk.delta)

            # Check budget after each chunk
            if not budget.consume(chunk.delta):
                print("\n  [BUDGET EXCEEDED -- stopping stream]")
                break

    elapsed_ms = int((time.time() - start) * 1000)
    config.print_stream_done(elapsed_ms, chunk_count)

    return "".join(collected), budget.exceeded


def create_provider(provider_name: str):
    """Create a provider, falling back to Ollama if no API key."""
    if provider_name == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ANTHROPIC_API_KEY not set -- falling back to Ollama")
            return Provider.ollama(model="llama3"), "llama3"
        return Provider.claude(
            model="claude-haiku-4-5-20251001", api_key=api_key
        ), "claude-haiku-4-5-20251001"

    if provider_name == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("Error: OPENAI_API_KEY not set")
            return None, None
        return Provider.openai(model="gpt-4o", api_key=api_key), "gpt-4o"

    if provider_name == "ollama":
        return Provider.ollama(model="llama3"), "llama3"

    print(f"Unknown provider: {provider_name}. Supported: claude, openai, ollama")
    return None, None


def main() -> int:
    config = InteractiveConfig.from_args()

    print("=== Token Budget with Streaming Example ===")
    print()

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    provider_name = args[0] if args else "claude"

    provider, model = create_provider(provider_name)
    if provider is None:
        return 1

    print(f"Using provider: {provider.provider_name} ({model})")
    print()

    # --- Demo 1: Small budget (will likely be exceeded) ---
    if (
        config.step_pause(
            "Demo 1: Small token budget (25 tokens)...",
            [
                "Sets a tight budget of 25 estimated tokens",
                "Stream will be cut short when budget is consumed",
                "Demonstrates cost-control via early cancellation",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Demo 1: Small budget (25 tokens) ---")
    small_budget = TokenBudget(max_tokens=25)

    messages = [
        Message.user("Write a detailed explanation of how neural networks learn."),
    ]

    try:
        text, exceeded = stream_with_budget(provider, messages, small_budget, config)
        print()
        print(f"  {small_budget.summary()}")
        print(f"  Output length: {len(text)} chars")
        if exceeded:
            print("  Result: Stream stopped early (budget control working)")
    except LLMError as e:
        print(f"\n  Error: {e}")
        return 1
    print()

    # --- Demo 2: Generous budget (should complete normally) ---
    if (
        config.step_pause(
            "Demo 2: Generous token budget (500 tokens)...",
            [
                "Sets a large budget of 500 tokens",
                "Response should complete naturally before budget is hit",
                "Shows that budget tracking is non-intrusive when limits are high",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Demo 2: Generous budget (500 tokens) ---")
    large_budget = TokenBudget(max_tokens=500)

    messages = [
        Message.user("Summarize the concept of token budgets in one paragraph."),
    ]

    try:
        text, exceeded = stream_with_budget(provider, messages, large_budget, config)
        print()
        print(f"  {large_budget.summary()}")
        print(f"  Output length: {len(text)} chars")
        if not exceeded:
            print("  Result: Completed within budget")
    except LLMError as e:
        print(f"\n  Error: {e}")
        return 1
    print()

    # --- Demo 3: stream_with_callback utility ---
    if (
        config.step_pause(
            "Demo 3: Using stream_with_callback for simpler streaming...",
            [
                "nxusKit: stream_with_callback handles iteration for you",
                "Callback receives each delta string as it arrives",
                "Returns a full ChatResponse with accumulated content",
            ],
        )
        == StepAction.QUIT
    ):
        return 0

    print("--- Demo 3: stream_with_callback (no budget, just display) ---")
    token_count = {"chars": 0}

    def on_chunk(delta: str) -> None:
        """Print each chunk and track character count."""
        print(delta, end="", flush=True)
        token_count["chars"] += len(delta)

    try:
        # nxusKit: stream_with_callback returns ChatResponse with full content
        response = stream_with_callback(
            provider.chat_stream(
                [Message.user("List three tips for managing API costs.")],
                max_tokens=200,
            ),
            on_chunk,
        )
        print()
        print(f"  Total chars: {token_count['chars']}")
        if response.usage.total_tokens > 0:
            print(f"  Actual tokens (from API): {response.usage.total_tokens}")
    except LLMError as e:
        print(f"\n  Error: {e}")
        return 1

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
