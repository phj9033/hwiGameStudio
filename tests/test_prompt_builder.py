import pytest
import tempfile
import os
from backend.services.prompt_builder import PromptBuilder


@pytest.fixture
def agents_dir():
    """Create temporary agents directory with test agent files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test agent markdown file
        agent_path = os.path.join(tmpdir, "test_agent.md")
        with open(agent_path, "w") as f:
            f.write("""# Test Agent

## Role
You are a test agent specialized in testing.

## Guidelines
- Write comprehensive tests
- Follow best practices
- Ensure code quality
""")
        yield tmpdir


def test_build_prompt_basic(agents_dir):
    """Test building a basic prompt with agent, ticket, and step info"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project: Game Engine\nPath: /projects/game",
        ticket_title="Implement combat system",
        ticket_description="Create a turn-based combat system with health tracking",
        step_instruction="Design the combat mechanics",
        context_refs=["docs/combat.md", "src/player.py"]
    )

    # Verify all sections are present
    assert "# Test Agent" in prompt
    assert "You are a test agent specialized in testing" in prompt
    assert "Project: Game Engine" in prompt
    assert "Implement combat system" in prompt
    assert "Create a turn-based combat system" in prompt
    assert "Design the combat mechanics" in prompt
    assert "docs/combat.md" in prompt
    assert "src/player.py" in prompt


def test_build_prompt_missing_agent(agents_dir):
    """Test building prompt when agent file doesn't exist"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="nonexistent_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="Test description",
        step_instruction="Test instruction",
        context_refs=[]
    )

    # Should still build prompt with warning
    assert "Agent file not found" in prompt
    assert "Test ticket" in prompt
    assert "Test instruction" in prompt


def test_build_prompt_no_context_refs(agents_dir):
    """Test building prompt with empty context_refs"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="Test description",
        step_instruction="Test instruction",
        context_refs=[]
    )

    assert "# Test Agent" in prompt
    assert "Test ticket" in prompt
    # Should handle empty context_refs gracefully
    assert prompt is not None


def test_build_prompt_with_empty_description(agents_dir):
    """Test building prompt with empty ticket description"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="",
        step_instruction="Test instruction",
        context_refs=[]
    )

    assert "Test ticket" in prompt
    assert "Test instruction" in prompt


def test_build_prompt_with_workspace_context(agents_dir):
    """Test building prompt with workspace context and .writing convention"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="Test description",
        step_instruction="Implement mechanics",
        context_refs=[],
        workspace_path="/tmp/workspace/ticket_1/",
        produces=["mechanics_spec.md"],
        depends_on=["gdd.md"]
    )

    # Verify workspace section is present
    assert "workspace" in prompt.lower() or "작업 공간" in prompt
    assert "/tmp/workspace/ticket_1/" in prompt

    # Verify .writing convention is explained
    assert ".writing" in prompt

    # Verify produces list is included
    assert "mechanics_spec.md" in prompt

    # Verify depends_on list is included
    assert "gdd.md" in prompt


def test_build_prompt_with_workspace_multiple_files(agents_dir):
    """Test workspace context with multiple produces and depends_on files"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="Test description",
        step_instruction="Create documentation",
        context_refs=[],
        workspace_path="/workspace/ticket_2/",
        produces=["tech_spec.md", "architecture.md", "api_docs.md"],
        depends_on=["gdd.md", "mechanics_spec.md"]
    )

    # Verify all produces files are listed
    assert "tech_spec.md" in prompt
    assert "architecture.md" in prompt
    assert "api_docs.md" in prompt

    # Verify all depends_on files are listed
    assert "gdd.md" in prompt
    assert "mechanics_spec.md" in prompt

    # Verify workspace path
    assert "/workspace/ticket_2/" in prompt


def test_build_prompt_workspace_without_produces_or_depends(agents_dir):
    """Test workspace context with only path, no produces or depends_on"""
    builder = PromptBuilder(agents_dir=agents_dir)

    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="Test description",
        step_instruction="Review code",
        context_refs=[],
        workspace_path="/workspace/ticket_3/"
    )

    # Verify workspace section exists
    assert "작업 공간" in prompt or "workspace" in prompt.lower()
    assert "/workspace/ticket_3/" in prompt
    assert ".writing" in prompt


def test_build_prompt_backward_compatibility(agents_dir):
    """Test that existing code without workspace params still works"""
    builder = PromptBuilder(agents_dir=agents_dir)

    # Call with old signature (no workspace params)
    prompt = builder.build_prompt(
        agent_name="test_agent",
        project_context="Project context",
        ticket_title="Test ticket",
        ticket_description="Test description",
        step_instruction="Test instruction",
        context_refs=["file1.md", "file2.md"]
    )

    # Verify basic prompt structure is intact
    assert "# Test Agent" in prompt
    assert "Test ticket" in prompt
    assert "Test instruction" in prompt
    assert "file1.md" in prompt
    assert "file2.md" in prompt

    # Verify no workspace section is present
    assert "작업 공간" not in prompt
