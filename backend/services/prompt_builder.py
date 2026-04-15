import os
from typing import List, Optional


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (metadata_dict, content_without_frontmatter)
    """
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    frontmatter = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    meta = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, body


class PromptBuilder:
    """Builds prompts for CLI agents by combining agent instructions with context"""

    def __init__(self, agents_dir: str):
        """
        Args:
            agents_dir: Directory containing agent markdown files
        """
        self.agents_dir = agents_dir

    def get_agent_model(self, agent_name: str, provider: str) -> Optional[str]:
        """Return the model override for the given agent and provider, or None."""
        agent_file = os.path.join(self.agents_dir, f"{agent_name}.md")
        if not os.path.exists(agent_file):
            return None
        with open(agent_file, "r") as f:
            meta, _ = _parse_frontmatter(f.read())
        key = f"{provider}_model"
        return meta.get(key) or None

    def build_prompt(
        self,
        agent_name: str,
        project_context: str,
        ticket_title: str,
        ticket_description: str,
        step_instruction: str,
        context_refs: List[str],
        workspace_path: Optional[str] = None,
        produces: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None
    ) -> str:
        """Build a complete prompt for the agent.

        Args:
            agent_name: Name of the agent (corresponds to markdown file)
            project_context: Project-level context information
            ticket_title: Title of the ticket
            ticket_description: Description of the ticket
            step_instruction: Specific instruction for this step
            context_refs: List of file paths for additional context
            workspace_path: Optional path to shared workspace directory
            produces: Optional list of files this agent should produce
            depends_on: Optional list of files available to read from other agents

        Returns:
            Complete prompt string ready to send to CLI
        """
        sections = []

        # 1. Agent instructions from markdown file (frontmatter stripped)
        agent_file = os.path.join(self.agents_dir, f"{agent_name}.md")
        if os.path.exists(agent_file):
            with open(agent_file, "r") as f:
                _, agent_content = _parse_frontmatter(f.read())
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

        # 6. Workspace context
        if workspace_path:
            # Normalize workspace path (remove trailing slash for consistency)
            ws_path = workspace_path.rstrip('/')

            sections.append("\n---\n## 공유 작업 공간 (Shared Workspace)\n")
            sections.append(f"\n작업 공간 경로: `{ws_path}`\n")

            sections.append("\n### 파일 작성 규칙\n")
            sections.append("- 결과물은 반드시 `{filename}.writing` 형태로 작성하세요\n")
            sections.append(f"- 예: `gdd.md`를 작성할 때 → `{ws_path}/gdd.md.writing`으로 저장\n")
            sections.append("- 작성이 완료되면 오케스트레이터가 자동으로 최종 파일명으로 변경합니다\n")
            sections.append("- 절대 `.writing` 확장자를 직접 제거하지 마세요\n")

            if produces:
                sections.append("\n### 생성해야 할 파일\n")
                for file in produces:
                    sections.append(f"- `{file}` (작성 시: `{file}.writing`)\n")

            if depends_on:
                sections.append("\n### 참조 가능한 파일\n")
                sections.append("다음 파일들은 이미 완성된 문서로, 작업 공간에서 참조할 수 있습니다:\n")
                for file in depends_on:
                    sections.append(f"- `{ws_path}/{file}`\n")

        return "".join(sections)
