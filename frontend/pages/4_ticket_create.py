import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, post
from components.pipeline_editor import pipeline_editor, validate_pipeline
import requests

st.set_page_config(page_title="Create Ticket", page_icon="🎫", layout="wide")

st.title("🎫 Create Ticket")

# Fetch projects for dropdown
try:
    projects = get("/api/projects").get("items", [])
except Exception as e:
    projects = []
    st.error(f"Failed to connect to backend: {e}")

if not projects:
    st.warning("No projects available. Please create a project first.")
    if st.button("Go to Dashboard"):
        st.switch_page("pages/1_dashboard.py")
    st.stop()

# Initialize session state
if "ai_generating" not in st.session_state:
    st.session_state.ai_generating = False
if "ai_tickets" not in st.session_state:
    st.session_state.ai_tickets = None
if "ai_task_description" not in st.session_state:
    st.session_state.ai_task_description = ""
if "ai_project_id" not in st.session_state:
    st.session_state.ai_project_id = None
if "ticket_mode" not in st.session_state:
    st.session_state.ticket_mode = "Manual Input"

# Mode selector
mode = st.radio(
    "Creation Mode",
    ["Manual Input", "AI Auto-Generate"],
    index=["Manual Input", "AI Auto-Generate"].index(st.session_state.ticket_mode),
    horizontal=True,
    disabled=st.session_state.ai_generating,
    key="mode_radio"
)
st.session_state.ticket_mode = mode

st.divider()

if mode == "Manual Input":
    st.subheader("Manual Ticket Creation")

    # Fetch available agents
    try:
        available_agents = get("/api/agents")
        agent_names = [a["name"] for a in available_agents] if available_agents else []
    except Exception:
        agent_names = []

    if not agent_names:
        st.warning("No agents found. Create .md files in the agents directory first.")
        st.stop()

    with st.form("create_ticket_manual"):
        project = st.selectbox(
            "Project*",
            options=[p["id"] for p in projects],
            format_func=lambda x: next(p["display_name"] for p in projects if p["id"] == x)
        )

        title = st.text_input("Title*", placeholder="e.g., Build combat system")
        description = st.text_area("Description", placeholder="Detailed description of the ticket", height=100)
        created_by = st.text_input("Created By", placeholder="Your name (optional)")

        st.divider()
        st.markdown("### Pipeline Configuration")
        st.caption("Define the steps and agents for this ticket")

        num_steps = st.number_input("Number of Steps", min_value=0, max_value=10, value=0)

        steps = []
        for step_idx in range(num_steps):
            with st.expander(f"Step {step_idx + 1}", expanded=True):
                num_agents = st.number_input("Number of Agents", min_value=1, max_value=10, value=1, key=f"num_agents_{step_idx}")
                agents = []
                for agent_idx in range(num_agents):
                    st.markdown(f"**Agent {agent_idx + 1}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        agent_name = st.selectbox("Agent", agent_names, key=f"agent_name_{step_idx}_{agent_idx}")
                    with col2:
                        cli_provider = st.selectbox("CLI Provider", ["claude", "codex"], key=f"provider_{step_idx}_{agent_idx}")
                    instruction = st.text_area("Instruction", key=f"instruction_{step_idx}_{agent_idx}", placeholder="What should this agent do?", height=100)
                    if agent_name:
                        agents.append({"agent_name": agent_name, "cli_provider": cli_provider, "instruction": instruction, "context_refs": []})
                if agents:
                    steps.append({"step_order": step_idx + 1, "agents": agents})

        submitted = st.form_submit_button("Create Ticket", type="primary")

    if submitted:
        if not title:
            st.error("Title is required")
        else:
            if steps:
                valid, error_msg = validate_pipeline(steps)
                if not valid:
                    st.error(f"Pipeline validation failed: {error_msg}")
                    st.stop()
            try:
                result = post("/api/tickets/", json={
                    "project_id": project,
                    "title": title,
                    "description": description,
                    "source": "manual",
                    "created_by": created_by,
                    "steps": steps
                })
                st.session_state.selected_ticket_id = result["id"]
                st.session_state.show_ticket_detail = True
                st.switch_page("pages/3_ticket_board.py")
            except Exception as e:
                st.error(f"Failed: {e}")

elif mode == "AI Auto-Generate":
    st.subheader("AI-Generated Ticket")

    # Fetch actual agent list from API
    try:
        available_agents = get("/api/agents")
        agent_list = [a["name"] for a in available_agents] if available_agents else []
    except Exception:
        agent_list = []

    if not agent_list:
        st.warning("No agents found. Create .md files in the agents directory first.")
        st.stop()

    # Show error from previous attempt
    if "ai_error" in st.session_state:
        st.error(f"Failed: {st.session_state.ai_error}")
        del st.session_state.ai_error

    # AI is generating - poll for result
    if st.session_state.ai_generating:
        import time
        st.warning("AI가 분석 중입니다. 자동으로 결과를 확인합니다...")
        job_id = st.session_state.get("ai_job_id")
        if job_id:
            try:
                job = get(f"/api/tickets/decompose/{job_id}")
                if job["status"] == "completed":
                    st.session_state.ai_tickets = job["result"].get("tickets", [])
                    st.session_state.ai_generating = False
                    st.rerun()
                elif job["status"] == "failed":
                    st.session_state.ai_error = job.get("error", "Unknown error")
                    st.session_state.ai_generating = False
                    st.rerun()
                else:
                    time.sleep(2)
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to check status: {e}")
                st.session_state.ai_generating = False
        st.stop()

    # Input form
    st.info("Describe your game feature and AI will decompose it into actionable tickets with agent assignments")

    with st.form("ai_generate_ticket"):
        ai_project = st.selectbox(
            "Project*",
            options=[p["id"] for p in projects],
            format_func=lambda x: next(p["display_name"] for p in projects if p["id"] == x),
            key="ai_project"
        )

        task_description = st.text_area(
            "Feature Description*",
            placeholder="e.g., Build a combat system with melee and ranged attacks, health bars, and damage feedback",
            height=200
        )

        st.caption(f"Available agents: {', '.join(agent_list)}")
        generate_button = st.form_submit_button("Generate Recommendations", type="primary")

    if generate_button:
        if not task_description:
            st.error("Feature description is required")
        else:
            # Start async job on backend
            try:
                job = post("/api/tickets/decompose", json={
                    "description": task_description,
                    "agent_list": agent_list
                })
                st.session_state.ai_job_id = job["job_id"]
                st.session_state.ai_generating = True
                st.session_state.ai_tickets = None
                st.session_state.ai_project_id = ai_project
                st.session_state.ticket_mode = "AI Auto-Generate"
            except Exception as e:
                st.error(f"Failed to start: {e}")
            st.rerun()

    # Show results
    if st.session_state.ai_tickets is not None:
        tickets = st.session_state.ai_tickets
        if tickets:
            st.success(f"Generated {len(tickets)} ticket recommendation(s)!")
            for idx, ticket in enumerate(tickets):
                with st.expander(f"Ticket {idx + 1}: {ticket['title']}", expanded=True):
                    st.markdown(f"**Description:** {ticket['description']}")
                    for step in ticket.get("steps", []):
                        st.markdown(f"  - Step {step['step_order']}:")
                        for agent in step.get("agents", []):
                            st.markdown(f"    - **{agent['agent_name']}** ({agent['cli_provider']}): {agent['instruction']}")
                    if st.button(f"Create This Ticket", key=f"create_{idx}"):
                        try:
                            clean_steps = []
                            for step in ticket.get("steps", []):
                                clean_agents = []
                                for agent in step.get("agents", []):
                                    clean_agents.append({
                                        "agent_name": agent.get("agent_name", ""),
                                        "cli_provider": agent.get("cli_provider", "claude"),
                                        "instruction": agent.get("instruction", ""),
                                        "context_refs": agent.get("context_refs", [])
                                    })
                                clean_steps.append({
                                    "step_order": step.get("step_order", 0),
                                    "agents": clean_agents
                                })
                            post("/api/tickets/", json={
                                "project_id": st.session_state.ai_project_id,
                                "title": ticket.get("title", ""),
                                "description": ticket.get("description", ""),
                                "source": "ai_generated",
                                "created_by": "AI",
                                "steps": clean_steps
                            })
                            st.success(f"Ticket '{ticket['title']}' created!")
                        except Exception as e:
                            st.error(f"Failed: {e}")
        else:
            st.warning("No tickets generated. Try providing more details.")

        if st.button("Clear Results"):
            st.session_state.ai_tickets = None
            st.rerun()
