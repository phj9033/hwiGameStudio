import streamlit as st
import requests
from backend.config import BACKEND_URL
from datetime import datetime

st.set_page_config(page_title="Ticket Board", page_icon="📋", layout="wide")

st.title("📋 Ticket Board")

# Fetch projects for filter
try:
    projects_response = requests.get(f"{BACKEND_URL}/api/projects", timeout=5)
    if projects_response.status_code == 200:
        projects = projects_response.json().get("items", [])
    else:
        projects = []
except requests.exceptions.RequestException:
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

with col2:
    st.write("")  # Spacer

with col3:
    if st.button("🔄 Refresh"):
        st.rerun()

# Create ticket button
if st.button("➕ Create New Ticket", type="primary"):
    st.switch_page("pages/4_ticket_create.py")

st.divider()

# Fetch tickets
try:
    params = {}
    if project_filter != "all":
        params["project_id"] = project_filter

    response = requests.get(f"{BACKEND_URL}/api/tickets/", params=params, timeout=5)

    if response.status_code == 200:
        data = response.json()
        tickets = data.get("items", [])
        total = data.get("total", 0)

        if total == 0:
            st.info("No tickets found. Create your first ticket!")
        else:
            st.caption(f"Showing {len(tickets)} of {total} tickets")

            # Group tickets by status
            status_groups = {
                "open": [],
                "assigned": [],
                "running": [],
                "completed": []
            }

            for ticket in tickets:
                status = ticket.get("status", "open")
                if status in status_groups:
                    status_groups[status].append(ticket)

            # Display in columns (Kanban style)
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
                                # Ticket card
                                st.markdown(f"**{ticket['title']}**")
                                st.caption(f"ID: {ticket['id']}")

                                # Project name
                                if projects:
                                    project_name = next(
                                        (p["display_name"] for p in projects if p["id"] == ticket["project_id"]),
                                        f"Project {ticket['project_id']}"
                                    )
                                    st.caption(f"📁 {project_name}")

                                # Source badge
                                source = ticket.get("source", "manual")
                                source_emoji = "✋" if source == "manual" else "🤖"
                                st.caption(f"{source_emoji} {source}")

                                # Created date
                                created_at = ticket.get("created_at", "")
                                if created_at:
                                    try:
                                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                                        st.caption(f"🕐 {dt.strftime('%Y-%m-%d %H:%M')}")
                                    except:
                                        pass

                                # View details button
                                if st.button("View Details", key=f"view_{ticket['id']}"):
                                    # Store ticket ID in session state
                                    st.session_state.selected_ticket_id = ticket['id']
                                    st.session_state.show_ticket_detail = True
                                    st.rerun()

                                st.markdown("---")

    else:
        st.error(f"Failed to fetch tickets: {response.status_code}")

except requests.exceptions.RequestException as e:
    st.error(f"Failed to connect to backend: {e}")
    st.info("Make sure the backend server is running on http://localhost:8000")

# Ticket detail modal/expander
if st.session_state.get("show_ticket_detail"):
    ticket_id = st.session_state.get("selected_ticket_id")

    try:
        detail_response = requests.get(f"{BACKEND_URL}/api/tickets/{ticket_id}", timeout=5)
        if detail_response.status_code == 200:
            ticket_detail = detail_response.json()

            with st.expander(f"📄 Ticket #{ticket_id}: {ticket_detail['title']}", expanded=True):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(f"**Description:** {ticket_detail.get('description', 'No description')}")
                    st.markdown(f"**Status:** {ticket_detail['status']}")
                    st.markdown(f"**Source:** {ticket_detail['source']}")
                    st.markdown(f"**Created By:** {ticket_detail.get('created_by', 'N/A')}")

                with col2:
                    if st.button("Close", key="close_detail"):
                        st.session_state.show_ticket_detail = False
                        st.rerun()

                # Display steps and agents
                steps = ticket_detail.get("steps", [])
                if steps:
                    st.markdown("### Pipeline Steps")
                    for step in steps:
                        with st.expander(f"Step {step['step_order']} - {step['status']}", expanded=True):
                            agents = step.get("agents", [])
                            if agents:
                                for agent in agents:
                                    st.markdown(f"**Agent:** {agent['agent_name']}")
                                    st.markdown(f"**Provider:** {agent['cli_provider']}")
                                    st.markdown(f"**Status:** {agent['status']}")
                                    st.markdown(f"**Instruction:** {agent.get('instruction', 'No instruction')}")

                                    # Show results if available
                                    if agent.get("result_summary"):
                                        st.markdown(f"**Result:** {agent['result_summary']}")
                                    if agent.get("estimated_cost"):
                                        st.markdown(f"**Cost:** ${agent['estimated_cost']:.4f}")

                                    st.markdown("---")
                            else:
                                st.caption("No agents")
                else:
                    st.info("No pipeline steps defined")

        else:
            st.error("Failed to fetch ticket details")

    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch ticket details: {e}")
