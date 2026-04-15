import pytest
from backend.services.token_parser import parse_claude_output, parse_codex_output


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


def test_parse_claude_output_total_tokens():
    """Test parsing 'Total input tokens: 1,234' format"""
    output = "Total input tokens: 1,234\nTotal output tokens: 5,678"
    result = parse_claude_output(output)
    assert result["input_tokens"] == 1234
    assert result["output_tokens"] == 5678


def test_parse_claude_output_json():
    """Test parsing JSON format"""
    output = '{"input_tokens": 100, "output_tokens": 200}'
    result = parse_claude_output(output)
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 200


def test_parse_claude_output_json_camelcase():
    """Test parsing JSON format with camelCase keys"""
    output = '{"inputTokens": 300, "outputTokens": 400}'
    result = parse_claude_output(output)
    assert result["input_tokens"] == 300
    assert result["output_tokens"] == 400


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
