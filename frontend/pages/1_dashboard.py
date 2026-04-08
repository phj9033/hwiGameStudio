import streamlit as st
import requests
from backend.config import BACKEND_URL

st.set_page_config(page_title="Project Dashboard", page_icon="📊", layout="wide")

st.title("📊 Project Dashboard")

# Create project form
with st.expander("➕ Create New Project", expanded=False):
    with st.form("create_project"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Project Name*", placeholder="my-game", help="Unique identifier (lowercase, no spaces)")
            display_name = st.text_input("Display Name*", placeholder="My Game", help="Human-readable name")
        with col2:
            engine = st.selectbox("Engine", ["godot", "unity", "unreal", "custom"], index=0)
            mode = st.selectbox("Mode", ["development", "design", "prototype", "production"], index=0)

        submitted = st.form_submit_button("Create Project", type="primary")

        if submitted:
            if not name or not display_name:
                st.error("Project name and display name are required")
            else:
                try:
                    response = requests.post(
                        f"{BACKEND_URL}/api/projects",
                        json={
                            "name": name,
                            "display_name": display_name,
                            "engine": engine,
                            "mode": mode
                        },
                        timeout=5
                    )
                    if response.status_code == 200:
                        st.success(f"✅ Project '{display_name}' created successfully!")
                        st.rerun()
                    else:
                        st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Failed to connect to backend: {e}")

# Filter and display projects
st.subheader("Projects")

col1, col2 = st.columns([3, 1])
with col1:
    status_filter = st.selectbox(
        "Filter by status",
        ["all", "active", "frozen"],
        index=0,
        label_visibility="collapsed"
    )
with col2:
    if st.button("🔄 Refresh"):
        st.rerun()

# Fetch projects
try:
    params = {}
    if status_filter != "all":
        params["status"] = status_filter

    response = requests.get(f"{BACKEND_URL}/api/projects", params=params, timeout=5)
    if response.status_code == 200:
        data = response.json()
        projects = data.get("items", [])
        total = data.get("total", 0)

        if total == 0:
            st.info("No projects found. Create your first project above!")
        else:
            st.caption(f"Showing {len(projects)} of {total} projects")

            # Display projects in a grid
            for project in projects:
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 2])

                    with col1:
                        # Status icon
                        status_icon = "✅" if project["status"] == "active" else "❄️"
                        st.markdown(f"### {status_icon} {project['display_name']}")
                        st.caption(f"`{project['name']}`")

                    with col2:
                        st.metric("Engine", project["engine"])

                    with col3:
                        st.metric("Mode", project["mode"])

                    with col4:
                        st.metric("Status", project["status"])

                    with col5:
                        if st.button("View Details", key=f"view_{project['id']}"):
                            st.switch_page("pages/2_project_detail.py")

                    st.divider()
    else:
        st.error(f"Failed to fetch projects: {response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"Failed to connect to backend: {e}")
    st.info("Make sure the backend server is running on http://localhost:8000")
