import streamlit as st
from frontend.api_client import get
from datetime import datetime

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
        with st.expander(f"📄 Ticket #{ticket_id}: {ticket_detail['title']}", expanded=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Description:** {ticket_detail.get('description', 'No description')}")
                st.markdown(f"**Status:** {ticket_detail['status']}")
                st.markdown(f"**Source:** {ticket_detail['source']}")
            with col2:
                if st.button("Close", key="close_detail"):
                    st.session_state.show_ticket_detail = False
                    st.rerun()

            steps = ticket_detail.get("steps", [])
            if steps:
                st.markdown("### Pipeline Steps")
                for step in steps:
                    with st.expander(f"Step {step['step_order']} - {step['status']}", expanded=True):
                        for agent in step.get("agents", []):
                            st.markdown(f"**Agent:** {agent['agent_name']} | **Provider:** {agent['cli_provider']} | **Status:** {agent['status']}")
                            st.markdown(f"**Instruction:** {agent.get('instruction', 'No instruction')}")
                            if agent.get("result_summary"):
                                st.markdown(f"**Result:** {agent['result_summary']}")
                            if agent.get("estimated_cost"):
                                st.markdown(f"**Cost:** ${agent['estimated_cost']:.4f}")
                            st.markdown("---")
    except Exception as e:
        st.error(f"Failed to fetch ticket details: {e}")
