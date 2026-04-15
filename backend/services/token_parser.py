import re
import json


def parse_claude_output(output: str) -> dict:
    """Parse Claude CLI output for token counts.

    Tries multiple known formats from Claude CLI output.

    Args:
        output: Raw CLI output text

    Returns:
        dict with 'input_tokens' and 'output_tokens' keys (may be None if not found)
    """
    # Try JSON format first (--output-format json)
    try:
        data = json.loads(output)
        if isinstance(data, dict):
            inp = data.get("input_tokens") or data.get("inputTokens")
            out = data.get("output_tokens") or data.get("outputTokens")
            if inp is not None and out is not None:
                return {"input_tokens": int(inp), "output_tokens": int(out)}
    except (json.JSONDecodeError, ValueError):
        pass

    # Pattern: "Total input tokens: 1,234" style
    inp_match = re.search(r'(?:total\s+)?input[\s_]*tokens?[=:\s]+([0-9,]+)', output, re.IGNORECASE)
    out_match = re.search(r'(?:total\s+)?output[\s_]*tokens?[=:\s]+([0-9,]+)', output, re.IGNORECASE)
    if inp_match and out_match:
        return {
            "input_tokens": int(inp_match.group(1).replace(",", "")),
            "output_tokens": int(out_match.group(1).replace(",", "")),
        }

    # Pattern: "input: 1234, output: 5678" or "input=1234 output=5678"
    match = re.search(r'input[=:\s]+([0-9,]+).*?output[=:\s]+([0-9,]+)', output, re.IGNORECASE | re.DOTALL)
    if match:
        return {
            "input_tokens": int(match.group(1).replace(",", "")),
            "output_tokens": int(match.group(2).replace(",", "")),
        }

    return {"input_tokens": None, "output_tokens": None}


def parse_codex_output(output: str) -> dict:
    """Parse Codex CLI output for token counts.

    Args:
        output: Raw CLI output text

    Returns:
        dict with 'input_tokens' and 'output_tokens' keys (may be None if not found)
    """
    return parse_claude_output(output)
