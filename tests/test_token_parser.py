import pytest
from backend.services.token_parser import parse_claude_output, parse_codex_output, calculate_cost


def test_parse_claude_output():
    """Test parsing Claude CLI output for token counts"""
    output = "Processing complete. Total tokens: input=8230, output=3120. Done."
    result = parse_claude_output(output)
    assert result["input_tokens"] == 8230
    assert result["output_tokens"] == 3120


def test_parse_claude_output_alternate_format():
    """Test parsing alternate format with colons"""
    output = "Stats: input: 1000, output: 500"
    result = parse_claude_output(output)
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 500


def test_parse_claude_output_failure():
    """Test parsing output with no token info returns None"""
    result = parse_claude_output("no token info here")
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_parse_codex_output():
    """Test parsing Codex CLI output for token counts"""
    output = "Execution finished. Tokens: input=5000, output=2000"
    result = parse_codex_output(output)
    assert result["input_tokens"] == 5000
    assert result["output_tokens"] == 2000


def test_parse_codex_output_failure():
    """Test parsing output with no token info returns None"""
    result = parse_codex_output("no token data")
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_calculate_cost():
    """Test cost calculation from token counts"""
    # input=8230, output=3120, rates=0.015/0.075 per 1K
    # (8230/1000 * 0.015) + (3120/1000 * 0.075) = 0.12345 + 0.234 = 0.35745
    cost = calculate_cost(8230, 3120, input_rate=0.015, output_rate=0.075)
    assert abs(cost - 0.35745) < 0.0001


def test_calculate_cost_zero_tokens():
    """Test cost with zero tokens"""
    cost = calculate_cost(0, 0, input_rate=0.015, output_rate=0.075)
    assert cost == 0.0


def test_calculate_cost_codex_rates():
    """Test cost calculation with codex rates"""
    # input=10000, output=5000, rates=0.003/0.015 per 1K
    # (10000/1000 * 0.003) + (5000/1000 * 0.015) = 0.03 + 0.075 = 0.105
    cost = calculate_cost(10000, 5000, input_rate=0.003, output_rate=0.015)
    assert abs(cost - 0.105) < 0.0001
