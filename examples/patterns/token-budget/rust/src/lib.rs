//! Streaming with Token Budget Pattern
//!
//! Demonstrates how to stream LLM responses while enforcing a token budget
//! to control costs.

use nxuskit::{ChatRequest, NxuskitError, NxuskitProvider};

/// Result of streaming with budget enforcement.
pub struct BudgetStreamResult {
    /// The accumulated content from the stream
    pub content: String,
    /// Estimated token count
    pub estimated_tokens: u32,
    /// Whether the budget was reached
    pub budget_reached: bool,
}

/// Streams a response from the provider while enforcing a token budget.
///
/// Uses a simple heuristic of ~4 characters per token for estimation.
/// Stops streaming when the estimated token count reaches the budget.
///
/// # Arguments
/// * `provider` - The LLM provider to use
/// * `request` - The chat request
/// * `max_tokens` - Maximum tokens to allow before stopping
///
/// # Returns
/// * `Ok(BudgetStreamResult)` - The streamed content with token info
/// * `Err(NxuskitError)` - If streaming fails
pub fn stream_with_budget(
    provider: &NxuskitProvider,
    request: &ChatRequest,
    max_tokens: u32,
) -> Result<BudgetStreamResult, NxuskitError> {
    let mut stream = provider.chat_stream(request.clone())?;
    let mut content = String::new();
    let mut budget_reached = false;

    while let Some(Ok(chunk)) = stream.next_chunk() {
        content.push_str(&chunk.delta);

        // Estimate tokens: ~4 characters per token (conservative)
        let estimated_tokens = (content.len() / 4) as u32;

        if estimated_tokens >= max_tokens {
            budget_reached = true;
            println!(
                "Budget reached ({} estimated tokens), stopping stream",
                estimated_tokens
            );
            break;
        }
    }

    let estimated_tokens = (content.len() / 4) as u32;
    Ok(BudgetStreamResult {
        content,
        estimated_tokens,
        budget_reached,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_budget_result_fields() {
        let result = BudgetStreamResult {
            content: "Hello world".into(),
            estimated_tokens: 2,
            budget_reached: false,
        };
        assert_eq!(result.content, "Hello world");
        assert_eq!(result.estimated_tokens, 2);
        assert!(!result.budget_reached);
    }

    #[test]
    fn test_budget_result_reached() {
        let result = BudgetStreamResult {
            content: "x".repeat(200),
            estimated_tokens: 50,
            budget_reached: true,
        };
        assert!(result.budget_reached);
        assert_eq!(result.estimated_tokens, 50);
    }
}
