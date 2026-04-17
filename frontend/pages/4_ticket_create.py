import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, post
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
if "manual_sessions" not in st.session_state:
    st.session_state.manual_sessions = []

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
        st.markdown("### Session Configuration")
        st.caption("Define the sessions for this ticket. Each session runs independently based on dependencies.")

        num_sessions = st.number_input("Number of Sessions", min_value=1, max_value=20, value=1)

        sessions = []
        for session_idx in range(num_sessions):
            with st.expander(f"Session {session_idx + 1}", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    agent_name = st.selectbox("Agent*", agent_names, key=f"agent_name_{session_idx}")
                with col2:
                    cli_provider = st.selectbox("CLI Provider", ["claude", "codex"], key=f"provider_{session_idx}")

                instruction = st.text_area("Instruction*", key=f"instruction_{session_idx}", placeholder="What should this agent do?", height=100)

                col1, col2 = st.columns(2)
                with col1:
                    depends_on_str = st.text_input("Depends On (comma-separated artifact names)", key=f"depends_on_{session_idx}", placeholder="e.g., design_doc, api_spec")
                with col2:
                    produces_str = st.text_input("Produces (comma-separated artifact names)", key=f"produces_{session_idx}", placeholder="e.g., combat_code, test_results")

                depends_on = [d.strip() for d in depends_on_str.split(",") if d.strip()] if depends_on_str else []
                produces = [p.strip() for p in produces_str.split(",") if p.strip()] if produces_str else []

                if agent_name and instruction:
                    sessions.append({
                        "agent_name": agent_name,
                        "cli_provider": cli_provider,
                        "instruction": instruction,
                        "depends_on": depends_on,
                        "produces": produces
                    })

        submitted = st.form_submit_button("Create Ticket", type="primary")

    if submitted:
        if not title:
            st.error("Title is required")
        elif not sessions:
            st.error("At least one session with agent and instruction is required")
        else:
            try:
                result = post("/api/tickets/", json={
                    "project_id": project,
                    "title": title,
                    "description": description,
                    "source": "manual",
                    "created_by": created_by,
                    "sessions": sessions
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
        st.warning("AI is analyzing. Checking for results automatically...")
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

            # Bulk create all tickets
            col_bulk1, col_bulk2 = st.columns([1, 1])
            with col_bulk1:
                if st.button("Create All Tickets", type="primary"):
                    created = 0
                    failed = 0
                    errors = []
                    for ticket in tickets:
                        try:
                            raw_sessions = ticket.get("sessions", [])
                            # Collect all produces within this ticket
                            internal_produces = set()
                            for s in raw_sessions:
                                internal_produces.update(s.get("produces", []))

                            clean_sessions = []
                            for session in raw_sessions:
                                # Filter depends_on to only include artifacts produced within this ticket
                                depends_on = [d for d in session.get("depends_on", []) if d in internal_produces]
                                clean_sessions.append({
                                    "agent_name": session.get("agent_name", ""),
                                    "cli_provider": session.get("cli_provider", "claude"),
                                    "instruction": session.get("instruction", ""),
                                    "depends_on": depends_on,
                                    "produces": session.get("produces", [])
                                })
                            post("/api/tickets/", json={
                                "project_id": st.session_state.ai_project_id,
                                "title": ticket.get("title", ""),
                                "description": ticket.get("description", ""),
                                "source": "ai_generated",
                                "created_by": "AI",
                                "sessions": clean_sessions
                            })
                            created += 1
                        except Exception as e:
                            failed += 1
                            errors.append(f"{ticket.get('title', '?')}: {e}")
                    if created:
                        st.success(f"{created}개 티켓 생성 완료!")
                    if failed:
                        st.error(f"{failed}개 티켓 생성 실패")
                        for err in errors:
                            st.caption(err)
            with col_bulk2:
                if st.button("Clear Results"):
                    st.session_state.ai_tickets = None
                    st.rerun()

            st.divider()

            for idx, ticket in enumerate(tickets):
                with st.expander(f"Ticket {idx + 1}: {ticket['title']}", expanded=True):
                    st.markdown(f"**Description:** {ticket['description']}")

                    # Display sessions
                    sessions = ticket.get("sessions", [])
                    if sessions:
                        st.markdown("**Sessions:**")
                        for session_idx, session in enumerate(sessions):
                            st.markdown(f"  {session_idx + 1}. **{session.get('agent_name', 'unknown')}** ({session.get('cli_provider', 'claude')})")
                            st.markdown(f"     - Instruction: {session.get('instruction', '')}")
                            if session.get("depends_on"):
                                st.markdown(f"     - Depends on: {', '.join(session['depends_on'])}")
                            if session.get("produces"):
                                st.markdown(f"     - Produces: {', '.join(session['produces'])}")

                    if st.button(f"Create This Ticket", key=f"create_{idx}"):
                        try:
                            # Collect all produces within this ticket
                            internal_produces = set()
                            for s in sessions:
                                internal_produces.update(s.get("produces", []))

                            clean_sessions = []
                            for session in sessions:
                                depends_on = [d for d in session.get("depends_on", []) if d in internal_produces]
                                clean_sessions.append({
                                    "agent_name": session.get("agent_name", ""),
                                    "cli_provider": session.get("cli_provider", "claude"),
                                    "instruction": session.get("instruction", ""),
                                    "depends_on": depends_on,
                                    "produces": session.get("produces", [])
                                })
                            post("/api/tickets/", json={
                                "project_id": st.session_state.ai_project_id,
                                "title": ticket.get("title", ""),
                                "description": ticket.get("description", ""),
                                "source": "ai_generated",
                                "created_by": "AI",
                                "sessions": clean_sessions
                            })
                            st.success(f"Ticket '{ticket['title']}' created!")
                        except Exception as e:
                            st.error(f"Failed: {e}")
        else:
            st.warning("No tickets generated. Try providing more details.")
