import json
import os
from typing import List, Dict
from backend.services.cli_runner import CLIRunner


class TicketAnalyzer:
    """AI-powered ticket decomposition and diff analysis"""

    def __init__(self):
        self.cli_runner = CLIRunner()

    async def decompose_task(self, description: str, agent_list: List[str]) -> Dict:
        """Analyze task description and decompose into tickets.

        Args:
            description: Natural language task description
            agent_list: List of available agent names

        Returns:
            Dict with 'tickets' key containing list of ticket recommendations

        Raises:
            ValueError: If AI response cannot be parsed as JSON
        """
        # Load prompt template
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "prompts",
            "decompose_task.md"
        )
        with open(template_path, "r") as f:
            template = f.read()

        # Build prompt
        prompt = template.format(
            task_description=description,
            agent_list=", ".join(agent_list)
        )

        # Call CLI runner with claude
        result = await self.cli_runner.run(
            command="claude --print",
            prompt=prompt,
            work_dir=os.getcwd(),
            env={}
        )

        # Parse JSON response
        try:
            response_data = json.loads(result["stdout"])
            return response_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response as JSON: {e}")

    async def analyze_diff(
        self,
        file_path: str,
        diff_content: str,
        agent_list: List[str]
    ) -> Dict:
        """Analyze document diff and recommend tickets.

        Args:
            file_path: Path to the changed document
            diff_content: Diff content showing changes
            agent_list: List of available agent names

        Returns:
            Dict with 'tickets' key containing list of ticket recommendations

        Raises:
            ValueError: If AI response cannot be parsed as JSON
        """
        # Load prompt template
        template_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "prompts",
            "analyze_diff.md"
        )
        with open(template_path, "r") as f:
            template = f.read()

        # Build prompt
        prompt = template.format(
            file_path=file_path,
            diff_content=diff_content,
            agent_list=", ".join(agent_list)
        )

        # Call CLI runner with claude
        result = await self.cli_runner.run(
            command="claude --print",
            prompt=prompt,
            work_dir=os.getcwd(),
            env={}
        )

        # Parse JSON response
        try:
            response_data = json.loads(result["stdout"])
            return response_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response as JSON: {e}")
