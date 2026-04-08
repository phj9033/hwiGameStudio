import re


def parse_claude_output(output: str) -> dict:
    """Parse Claude CLI output for token counts.

    Args:
        output: Raw CLI output text

    Returns:
        dict with 'input_tokens' and 'output_tokens' keys (may be None if not found)
    """
    match = re.search(r'input[=:\s]+(\d+).*?output[=:\s]+(\d+)', output, re.IGNORECASE | re.DOTALL)
    if match:
        return {"input_tokens": int(match.group(1)), "output_tokens": int(match.group(2))}
    return {"input_tokens": None, "output_tokens": None}


def parse_codex_output(output: str) -> dict:
    """Parse Codex CLI output for token counts.

    Args:
        output: Raw CLI output text

    Returns:
        dict with 'input_tokens' and 'output_tokens' keys (may be None if not found)
    """
    match = re.search(r'input[=:\s]+(\d+).*?output[=:\s]+(\d+)', output, re.IGNORECASE | re.DOTALL)
    if match:
        return {"input_tokens": int(match.group(1)), "output_tokens": int(match.group(2))}
    return {"input_tokens": None, "output_tokens": None}


def calculate_cost(input_tokens: int, output_tokens: int, input_rate: float, output_rate: float) -> float:
    """Calculate cost from token counts and rates.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        input_rate: Cost per 1K input tokens
        output_rate: Cost per 1K output tokens

    Returns:
        Total cost in dollars
    """
    return (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)
