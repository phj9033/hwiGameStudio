import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, post, delete
from datetime import datetime, timezone

st.set_page_config(page_title="Ticket Board", page_icon="📋", layout="wide")

st.title("📋 Ticket Board")

# Fetch projects for filter
try:
    projects = get("/api/projects").get("items", [])
except Exception:
    projects = []

# Filter controls
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    if projects:
        project_filter = st.selectbox(
            "Filter by Project",
            options=["all"] + [p["id"] for p in projects],
            format_func=lambda x: "All Projects" if x == "all" else next((p["display_name"] for p in projects if p["id"] == x), "Unknown")
        )
    else:
        project_filter = "all"
        st.info("No projects found")

with col3:
    if st.button("🔄 Refresh"):
        st.rerun()

if st.button("➕ Create New Ticket", type="primary"):
    st.switch_page("pages/4_ticket_create.py")

st.divider()

# Fetch tickets
try:
    params = {}
    if project_filter != "all":
        params["project_id"] = project_filter

    data = get("/api/tickets/", params=params)
    tickets = data.get("items", [])
    total = data.get("total", 0)

    if total == 0:
        st.info("No tickets found. Create your first ticket!")
    else:
        st.caption(f"Showing {len(tickets)} of {total} tickets")

        status_groups = {"open": [], "assigned": [], "running": [], "completed": []}
        for ticket in tickets:
            status = ticket.get("status", "open")
            if status in status_groups:
                status_groups[status].append(ticket)

        col1, col2, col3, col4 = st.columns(4)
        columns = [
            (col1, "open", "📝 Open", status_groups["open"]),
            (col2, "assigned", "👥 Assigned", status_groups["assigned"]),
            (col3, "running", "🚀 Running", status_groups["running"]),
            (col4, "completed", "✅ Completed", status_groups["completed"])
        ]

        for col, status_key, status_label, tickets_list in columns:
            with col:
                st.markdown(f"### {status_label}")
                st.markdown(f"**{len(tickets_list)}** tickets")
                st.divider()

                if not tickets_list:
                    st.caption("No tickets")
                else:
                    for ticket in tickets_list:
                        with st.container():
                            st.markdown(f"**{ticket['title']}**")
                            st.caption(f"ID: {ticket['id']}")
                            if projects:
                                project_name = next(
                                    (p["display_name"] for p in projects if p["id"] == ticket["project_id"]),
                                    f"Project {ticket['project_id']}"
                                )
                                st.caption(f"📁 {project_name}")
                            source = ticket.get("source", "manual")
                            source_emoji = "✋" if source == "manual" else "🤖"
                            st.caption(f"{source_emoji} {source}")
                            if st.button("View Details", key=f"view_{ticket['id']}"):
                                st.session_state.selected_ticket_id = ticket['id']
                                st.session_state.show_ticket_detail = True
                                st.rerun()
                            st.markdown("---")

except Exception as e:
    st.error(f"Failed to connect to backend: {e}")

# Ticket detail
if st.session_state.get("show_ticket_detail"):
    ticket_id = st.session_state.get("selected_ticket_id")
    try:
        ticket_detail = get(f"/api/tickets/{ticket_id}")
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### 📄 Ticket #{ticket_id}: {ticket_detail['title']}")
            st.markdown(f"**Description:** {ticket_detail.get('description', 'No description')}")
            st.markdown(f"**Status:** {ticket_detail['status']} | **Source:** {ticket_detail['source']}")
        with col2:
            if st.button("Close", key="close_detail"):
                st.session_state.show_ticket_detail = False
                st.rerun()

        # Action buttons based on ticket status
        ticket_status = ticket_detail["status"]
        action_cols = st.columns(4)
        with action_cols[0]:
            if ticket_status in ("assigned", "open") and ticket_detail.get("steps"):
                if st.button("▶️ Run", key="run_ticket", type="primary", use_container_width=True):
                    try:
                        post(f"/api/tickets/{ticket_id}/run")
                        st.success("Ticket execution started!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
        with action_cols[1]:
            if ticket_status == "running":
                if st.button("⏹️ Cancel", key="cancel_ticket", use_container_width=True):
                    try:
                        post(f"/api/tickets/{ticket_id}/cancel")
                        st.success("Ticket cancelled!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
        with action_cols[2]:
            if ticket_status == "failed":
                if st.button("🔄 Retry", key="retry_ticket", use_container_width=True):
                    try:
                        post(f"/api/tickets/{ticket_id}/retry")
                        st.success("Retrying failed steps!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
        with action_cols[3]:
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔄 Refresh", key="refresh_detail", use_container_width=True):
                    st.rerun()
            with col_b:
                if ticket_status != "running":
                    if st.button("🗑️ Delete", key="delete_ticket", use_container_width=True):
                        try:
                            delete(f"/api/tickets/{ticket_id}")
                            st.success("Ticket deleted!")
                            st.session_state.show_ticket_detail = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")

        steps = ticket_detail.get("steps", [])
        if steps:
            # Progress bar & summary when running
            total_steps = len(steps)
            completed_steps = sum(1 for s in steps if s["status"] == "completed")

            if ticket_status == "running":
                st.markdown("#### Pipeline Progress")
                progress_value = completed_steps / total_steps if total_steps > 0 else 0
                st.progress(progress_value, text=f"Step {completed_steps + 1} / {total_steps} running...")

                # Find currently running agent and show elapsed time
                for step in steps:
                    for agent in step.get("agents", []):
                        if agent["status"] == "running" and agent.get("started_at"):
                            try:
                                started = datetime.fromisoformat(agent["started_at"])
                                now = datetime.now(timezone.utc) if started.tzinfo else datetime.now()
                                elapsed = now - started
                                mins, secs = divmod(int(elapsed.total_seconds()), 60)
                                st.info(
                                    f"▶️ **{agent['agent_name']}** running for "
                                    f"**{mins}m {secs}s** (provider: {agent['cli_provider']})"
                                )
                            except Exception:
                                st.info(f"▶️ **{agent['agent_name']}** running...")
            else:
                st.markdown("#### Pipeline Steps")

            for step in steps:
                status_icon = {"pending": "⏳", "running": "▶️", "completed": "✅", "failed": "❌", "cancelled": "⏹️"}.get(step["status"], "❓")
                with st.expander(f"{status_icon} Step {step['step_order']} - {step['status']}", expanded=(step["status"] in ("running", "failed"))):
                    for agent in step.get("agents", []):
                        agent_icon = {"pending": "⏳", "running": "▶️", "completed": "✅", "failed": "❌", "cancelled": "⏹️"}.get(agent["status"], "❓")
                        st.markdown(f"**{agent_icon} {agent['agent_name']}** | Provider: {agent['cli_provider']} | Status: {agent['status']}")

                        # Show elapsed time for running agent
                        if agent["status"] == "running" and agent.get("started_at"):
                            try:
                                started = datetime.fromisoformat(agent["started_at"])
                                now = datetime.now(timezone.utc) if started.tzinfo else datetime.now()
                                elapsed = now - started
                                mins, secs = divmod(int(elapsed.total_seconds()), 60)
                                st.caption(f"⏱️ Elapsed: {mins}m {secs}s")
                            except Exception:
                                pass

                        # Show duration for completed agent
                        if agent["status"] == "completed" and agent.get("started_at") and agent.get("completed_at"):
                            try:
                                started = datetime.fromisoformat(agent["started_at"])
                                completed = datetime.fromisoformat(agent["completed_at"])
                                duration = completed - started
                                mins, secs = divmod(int(duration.total_seconds()), 60)
                                st.caption(f"⏱️ Duration: {mins}m {secs}s")
                            except Exception:
                                pass

                        st.markdown(f"**Instruction:** {agent.get('instruction', 'No instruction')}")
                        if agent.get("result_summary"):
                            if agent["status"] == "failed":
                                st.error(f"**Error:** {agent['result_summary']}")
                            else:
                                st.markdown(f"**Result:** {agent['result_summary']}")
                        if agent.get("input_tokens") or agent.get("output_tokens"):
                            st.caption(f"Tokens: {agent.get('input_tokens', 0):,} in / {agent.get('output_tokens', 0):,} out")
                        if agent.get("estimated_cost"):
                            st.caption(f"Cost: ${agent['estimated_cost']:.4f}")
                        st.markdown("---")
        elif ticket_status in ("open", "assigned"):
            st.info("No pipeline steps defined. This ticket has no executable steps.")

        # Auto-refresh when running
        if ticket_status == "running":
            import time
            time.sleep(10)
            st.rerun()
    except Exception as e:
        st.error(f"Failed to fetch ticket details: {e}")
