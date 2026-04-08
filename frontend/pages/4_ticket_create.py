import streamlit as st
import requests
from backend.config import BACKEND_URL
import sys
sys.path.append("/Users/ad03159868/Downloads/Claude_lab/hwire")
from frontend.components.pipeline_editor import pipeline_editor, validate_pipeline

st.set_page_config(page_title="Create Ticket", page_icon="🎫", layout="wide")

st.title("🎫 Create Ticket")

# Fetch projects for dropdown
try:
    projects_response = requests.get(f"{BACKEND_URL}/api/projects", timeout=5)
    if projects_response.status_code == 200:
        projects = projects_response.json().get("items", [])
    else:
        projects = []
        st.error("Failed to fetch projects")
except requests.exceptions.RequestException as e:
    projects = []
    st.error(f"Failed to connect to backend: {e}")

if not projects:
    st.warning("No projects available. Please create a project first.")
    if st.button("Go to Dashboard"):
        st.switch_page("pages/1_dashboard.py")
    st.stop()

# Tabs for manual and AI-generated tickets
tab1, tab2 = st.tabs(["Manual Input", "AI Auto-Generate"])

with tab1:
    st.subheader("Manual Ticket Creation")

    with st.form("create_ticket_manual"):
        # Basic info
        project = st.selectbox(
            "Project*",
            options=[p["id"] for p in projects],
            format_func=lambda x: next(p["display_name"] for p in projects if p["id"] == x)
        )

        title = st.text_input("Title*", placeholder="e.g., Build combat system")
        description = st.text_area(
            "Description",
            placeholder="Detailed description of the ticket",
            height=100
        )

        created_by = st.text_input("Created By", placeholder="Your name (optional)")

        st.divider()

        # Pipeline editor embedded in form
        st.markdown("### Pipeline Configuration")
        st.caption("Define the steps and agents for this ticket")

        # We can't use the component directly in a form, so we'll use a simplified version
        num_steps = st.number_input("Number of Steps", min_value=0, max_value=10, value=0)

        steps = []
        for step_idx in range(num_steps):
            with st.expander(f"Step {step_idx + 1}", expanded=True):
                num_agents = st.number_input(
                    "Number of Agents",
                    min_value=1,
                    max_value=10,
                    value=1,
                    key=f"num_agents_{step_idx}"
                )

                agents = []
                for agent_idx in range(num_agents):
                    st.markdown(f"**Agent {agent_idx + 1}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        agent_name = st.text_input(
                            "Agent Name",
                            key=f"agent_name_{step_idx}_{agent_idx}",
                            placeholder="e.g., sr_game_designer"
                        )
                    with col2:
                        cli_provider = st.selectbox(
                            "CLI Provider",
                            ["claude", "codex"],
                            key=f"provider_{step_idx}_{agent_idx}"
                        )

                    instruction = st.text_area(
                        "Instruction",
                        key=f"instruction_{step_idx}_{agent_idx}",
                        placeholder="What should this agent do?",
                        height=100
                    )

                    if agent_name:
                        agents.append({
                            "agent_name": agent_name,
                            "cli_provider": cli_provider,
                            "instruction": instruction,
                            "context_refs": []
                        })

                if agents:
                    steps.append({
                        "step_order": step_idx + 1,
                        "agents": agents
                    })

        submitted = st.form_submit_button("Create Ticket", type="primary")

        if submitted:
            if not title:
                st.error("Title is required")
            else:
                # Validate pipeline if steps are provided
                if steps:
                    valid, error_msg = validate_pipeline(steps)
                    if not valid:
                        st.error(f"Pipeline validation failed: {error_msg}")
                        st.stop()

                try:
                    response = requests.post(
                        f"{BACKEND_URL}/api/tickets/",
                        json={
                            "project_id": project,
                            "title": title,
                            "description": description,
                            "source": "manual",
                            "created_by": created_by,
                            "steps": steps
                        },
                        timeout=10
                    )
                    if response.status_code == 200:
                        st.success(f"Ticket '{title}' created successfully!")
                        st.balloons()
                        if st.button("Go to Ticket Board"):
                            st.switch_page("pages/3_ticket_board.py")
                    else:
                        st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to connect to backend: {e}")

with tab2:
    st.subheader("AI-Generated Ticket")
    st.info("AI ticket generation will be implemented in Task 7: AI Ticket Analyzer")

    st.markdown("""
    This feature will allow you to:
    - Describe a game feature in natural language
    - AI analyzes and generates a multi-step pipeline
    - Automatically assigns agents to each step
    - Suggests context documents and instructions
    """)

    st.text_area("Feature Description (Coming Soon)", disabled=True, height=200)
    st.button("Generate Ticket", disabled=True)
