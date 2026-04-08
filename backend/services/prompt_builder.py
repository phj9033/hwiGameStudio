import os
from typing import List


class PromptBuilder:
    """Builds prompts for CLI agents by combining agent instructions with context"""

    def __init__(self, agents_dir: str):
        """
        Args:
            agents_dir: Directory containing agent markdown files
        """
        self.agents_dir = agents_dir

    def build_prompt(
        self,
        agent_name: str,
        project_context: str,
        ticket_title: str,
        ticket_description: str,
        step_instruction: str,
        context_refs: List[str]
    ) -> str:
        """Build a complete prompt for the agent.

        Args:
            agent_name: Name of the agent (corresponds to markdown file)
            project_context: Project-level context information
            ticket_title: Title of the ticket
            ticket_description: Description of the ticket
            step_instruction: Specific instruction for this step
            context_refs: List of file paths for additional context

        Returns:
            Complete prompt string ready to send to CLI
        """
        sections = []

        # 1. Agent instructions from markdown file
        agent_file = os.path.join(self.agents_dir, f"{agent_name}.md")
        if os.path.exists(agent_file):
            with open(agent_file, "r") as f:
                agent_content = f.read()
            sections.append(agent_content)
        else:
            sections.append(f"# Agent file not found: {agent_name}\n")

        # 2. Project context
        if project_context:
            sections.append("\n---\n## Project Context\n")
            sections.append(project_context)

        # 3. Ticket information
        sections.append("\n---\n## Ticket\n")
        sections.append(f"**Title:** {ticket_title}\n")
        if ticket_description:
            sections.append(f"\n**Description:**\n{ticket_description}\n")

        # 4. Step instruction
        sections.append("\n---\n## Your Task\n")
        sections.append(step_instruction)

        # 5. Context references
        if context_refs:
            sections.append("\n---\n## Context References\n")
            sections.append("The following files are relevant to this task:\n")
            for ref in context_refs:
                sections.append(f"- {ref}\n")

        return "".join(sections)
