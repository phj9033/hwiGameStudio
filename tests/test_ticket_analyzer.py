import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from backend.services.ticket_analyzer import TicketAnalyzer
import json


@pytest.mark.asyncio
async def test_decompose_task():
    """Test decomposing task description into tickets"""
    mock_response = {
        "stdout": json.dumps({
            "tickets": [
                {
                    "title": "Design combat system",
                    "description": "Create initial combat design",
                    "sessions": [
                        {
                            "agent_name": "sr_game_designer",
                            "cli_provider": "claude",
                            "instruction": "Design combat mechanics",
                            "depends_on": [],
                            "produces": ["combat_design.md"]
                        }
                    ]
                }
            ]
        }),
        "stderr": "",
        "return_code": 0,
        "input_tokens": 100,
        "output_tokens": 200,
        "pid": 12345
    }

    with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_response

        analyzer = TicketAnalyzer()
        result = await analyzer.decompose_task(
            "Build a combat system",
            ["sr_game_designer", "mechanics_developer"]
        )

    assert len(result["tickets"]) == 1
    assert result["tickets"][0]["title"] == "Design combat system"
    assert len(result["tickets"][0]["sessions"]) == 1


@pytest.mark.asyncio
async def test_analyze_diff():
    """Test analyzing document diff and recommending tickets"""
    mock_response = {
        "stdout": json.dumps({
            "tickets": [
                {
                    "title": "Implement new combat feature",
                    "description": "Based on design changes",
                    "sessions": [
                        {
                            "agent_name": "mechanics_developer",
                            "cli_provider": "codex",
                            "instruction": "Implement combat feature",
                            "depends_on": [],
                            "produces": ["combat_feature.gd"]
                        }
                    ]
                }
            ]
        }),
        "stderr": "",
        "return_code": 0,
        "input_tokens": 150,
        "output_tokens": 250,
        "pid": 12346
    }

    with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_response

        analyzer = TicketAnalyzer()
        result = await analyzer.analyze_diff(
            "design/combat.md",
            "+New combat feature\n-Old feature",
            ["mechanics_developer"]
        )

    assert len(result["tickets"]) == 1
    assert result["tickets"][0]["title"] == "Implement new combat feature"


@pytest.mark.asyncio
async def test_decompose_task_invalid_json():
    """Test handling of invalid JSON response"""
    mock_response = {
        "stdout": "This is not valid JSON",
        "stderr": "",
        "return_code": 0,
        "input_tokens": 100,
        "output_tokens": 50,
        "pid": 12347
    }

    with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_response

        analyzer = TicketAnalyzer()
        with pytest.raises(ValueError, match="Failed to parse"):
            await analyzer.decompose_task(
                "Build something",
                ["some_agent"]
            )


@pytest.mark.asyncio
async def test_analyze_diff_invalid_json():
    """Test handling of invalid JSON response in diff analysis"""
    mock_response = {
        "stdout": "Not JSON at all",
        "stderr": "",
        "return_code": 0,
        "input_tokens": 100,
        "output_tokens": 50,
        "pid": 12348
    }

    with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_response

        analyzer = TicketAnalyzer()
        with pytest.raises(ValueError, match="Failed to parse"):
            await analyzer.analyze_diff(
                "file.md",
                "diff content",
                ["agent"]
            )
