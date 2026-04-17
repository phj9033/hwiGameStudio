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

        status_groups = {"open": [], "assigned": [], "running": [], "completed": [], "failed": [], "cancelled": []}
        for ticket in tickets:
            status = ticket.get("status", "open")
            if status in status_groups:
                status_groups[status].append(ticket)

        col1, col2, col3, col4, col5 = st.columns(5)
        columns = [
            (col1, "open", "📝 Open", status_groups["open"]),
            (col2, "assigned", "👥 Assigned", status_groups["assigned"]),
            (col3, "running", "🚀 Running", status_groups["running"]),
            (col4, "completed", "✅ Completed", status_groups["completed"]),
            (col5, "failed", "❌ Failed", status_groups["failed"] + status_groups["cancelled"])
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
            if ticket_status in ("assigned", "open") and ticket_detail.get("sessions"):
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
            if ticket_status in ("failed", "cancelled"):
                if st.button("🔄 Retry All", key="retry_ticket", type="primary", use_container_width=True):
                    try:
                        post(f"/api/tickets/{ticket_id}/retry")
                        st.success("Ticket retry started!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
        with action_cols[2]:
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

        sessions = ticket_detail.get("sessions", [])
        if sessions:
            # Progress bar & summary when running
            total_sessions = len(sessions)
            completed_sessions = sum(1 for s in sessions if s["status"] == "completed")
            failed_sessions = sum(1 for s in sessions if s["status"] == "failed")
            running_sessions = sum(1 for s in sessions if s["status"] == "running")

            if ticket_status == "running":
                st.markdown("#### Pipeline Progress")
                progress_value = completed_sessions / total_sessions if total_sessions > 0 else 0
                st.progress(progress_value, text=f"{completed_sessions} completed / {running_sessions} running / {total_sessions} total")

                # Find currently running sessions and show elapsed time
                for session in sessions:
                    if session["status"] == "running" and session.get("started_at"):
                        try:
                            started = datetime.fromisoformat(session["started_at"])
                            now = datetime.now(timezone.utc) if started.tzinfo else datetime.now()
                            elapsed = now - started
                            mins, secs = divmod(int(elapsed.total_seconds()), 60)
                            st.info(
                                f"▶️ **{session['agent_name']}** running for "
                                f"**{mins}m {secs}s** (provider: {session['cli_provider']})"
                            )
                        except Exception:
                            st.info(f"▶️ **{session['agent_name']}** running...")
            else:
                st.markdown("#### Sessions")
                if failed_sessions > 0:
                    st.caption(f"{completed_sessions} completed, {failed_sessions} failed, {total_sessions} total")
                else:
                    st.caption(f"{completed_sessions} completed / {total_sessions} total")

            # Display sessions as cards
            for session in sessions:
                status = session["status"]
                status_config = {
                    "pending": {"icon": "⏳", "color": "#808080", "label": "Pending"},
                    "waiting": {"icon": "⏸️", "color": "#FFA500", "label": "Waiting"},
                    "running": {"icon": "▶️", "color": "#1E90FF", "label": "Running"},
                    "completed": {"icon": "✅", "color": "#32CD32", "label": "Completed"},
                    "failed": {"icon": "❌", "color": "#DC143C", "label": "Failed"},
                    "cancelled": {"icon": "⏹️", "color": "#808080", "label": "Cancelled"}
                }
                config = status_config.get(status, {"icon": "❓", "color": "#808080", "label": status})

                expanded = status in ("running", "failed")
                with st.expander(f"{config['icon']} **{session['agent_name']}** - {config['label']}", expanded=expanded):
                    # Status badge
                    st.markdown(
                        f"<span style='background-color:{config['color']};color:white;padding:4px 8px;border-radius:4px;font-size:12px;font-weight:bold;'>"
                        f"{config['label']}</span>",
                        unsafe_allow_html=True
                    )

                    # Basic info
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Provider:** {session['cli_provider']}")
                        if session.get("depends_on"):
                            st.markdown(f"**Depends on:** {', '.join(session['depends_on'])}")
                    with col2:
                        if session.get("produces"):
                            st.markdown(f"**Produces:** {', '.join(session['produces'])}")

                    # Show waiting reason for waiting sessions
                    if status == "waiting" and session.get("depends_on"):
                        st.warning(f"⏸️ Waiting for: {', '.join(session['depends_on'])}")

                    # Show instruction
                    if session.get("instruction"):
                        st.markdown(f"**Instruction:** {session['instruction']}")

                    # Show elapsed time for running sessions
                    if status == "running" and session.get("started_at"):
                        try:
                            started = datetime.fromisoformat(session["started_at"])
                            now = datetime.now(timezone.utc) if started.tzinfo else datetime.now()
                            elapsed = now - started
                            mins, secs = divmod(int(elapsed.total_seconds()), 60)
                            st.caption(f"⏱️ Elapsed: {mins}m {secs}s")
                        except Exception:
                            pass

                    # Show duration for completed sessions
                    if status == "completed" and session.get("started_at") and session.get("completed_at"):
                        try:
                            started = datetime.fromisoformat(session["started_at"])
                            completed = datetime.fromisoformat(session["completed_at"])
                            duration = completed - started
                            mins, secs = divmod(int(duration.total_seconds()), 60)
                            st.caption(f"⏱️ Duration: {mins}m {secs}s")
                        except Exception:
                            pass

                    # Show error message for failed sessions
                    if status == "failed" and session.get("error_message"):
                        st.error(f"**Error:** {session['error_message']}")

                    # Show token usage
                    if session.get("input_tokens") or session.get("output_tokens"):
                        st.caption(f"Tokens: {session.get('input_tokens', 0):,} in / {session.get('output_tokens', 0):,} out")

                    # Retry button for failed sessions
                    if status == "failed":
                        if st.button(f"🔄 Retry Session", key=f"retry_session_{session['id']}"):
                            try:
                                post(f"/api/sessions/{session['id']}/retry")
                                st.success("Session retry initiated!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to retry: {e}")

                    # View session details button
                    if status in ("completed", "failed"):
                        if st.button(f"👁️ View Details", key=f"view_session_{session['id']}"):
                            st.session_state.selected_session_id = session['id']
                            st.session_state.show_session_viewer = True
                            st.rerun()

        elif ticket_status in ("open", "assigned"):
            st.info("No sessions defined. This ticket has no executable sessions.")

        # Auto-refresh when running
        if ticket_status == "running":
            import time
            time.sleep(10)
            st.rerun()
    except Exception as e:
        st.error(f"Failed to fetch ticket details: {e}")

# Session viewer modal
if st.session_state.get("show_session_viewer"):
    from components.result_viewer import render_session_viewer
    session_id = st.session_state.get("selected_session_id")
    st.divider()
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### 🔍 Session #{session_id} Details")
    with col2:
        if st.button("Close Viewer", key="close_session_viewer"):
            st.session_state.show_session_viewer = False
            st.rerun()
    render_session_viewer(session_id)
