import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, post, patch

st.set_page_config(page_title="Project Details", page_icon="📋", layout="wide")

st.title("📋 Project Details")

# Project selector
try:
    data = get("/api/projects", params={"per_page": 100})
    projects = data.get("items", [])

    if not projects:
        st.warning("No projects found. Create a project first on the Dashboard.")
        if st.button("Go to Dashboard"):
            st.switch_page("pages/1_dashboard.py")
        st.stop()

    project_options = {f"{p['display_name']} ({p['name']})": p for p in projects}
    selected_name = st.selectbox("Select Project", options=list(project_options.keys()), index=0)
    project = project_options[selected_name]
    project_id = project["id"]

except Exception as e:
    st.error(f"Failed to connect to backend: {e}")
    st.stop()

# Display project info
st.divider()

status_icon = "✅" if project["status"] == "active" else "❄️"
st.markdown(f"## {status_icon} {project['display_name']}")
st.caption(f"Project ID: `{project['name']}` | Created: {project['created_at']}")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Engine", project["engine"])
with col2:
    st.metric("Mode", project["mode"])
with col3:
    st.metric("Status", project["status"])
with col4:
    st.metric("Last Updated", project["updated_at"][:10])

st.divider()

# Action buttons
st.subheader("Actions")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if project["status"] == "active":
        if st.button("❄️ Freeze Project", use_container_width=True):
            try:
                post(f"/api/projects/{project_id}/freeze")
                st.success("Project frozen successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

with col2:
    if project["status"] == "frozen":
        if st.button("▶️ Resume Project", use_container_width=True):
            try:
                post(f"/api/projects/{project_id}/resume")
                st.success("Project resumed successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

with col3:
    if st.button("🔄 Start Over", use_container_width=True, type="secondary"):
        with st.expander("⚠️ Confirm Start Over", expanded=True):
            st.warning("This will reset the project to active status and cancel all active tickets.")
            confirm = st.checkbox("I understand this action cannot be undone")
            if st.button("Confirm Start Over", type="primary", disabled=not confirm):
                try:
                    post(f"/api/projects/{project_id}/startover")
                    st.success("Project reset successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

with col4:
    if st.button("📊 Back to Dashboard", use_container_width=True):
        st.switch_page("pages/1_dashboard.py")

st.divider()

# Project configuration
st.subheader("Configuration")

with st.expander("View/Edit Configuration", expanded=False):
    with st.form("update_project"):
        col1, col2 = st.columns(2)
        with col1:
            new_display_name = st.text_input("Display Name", value=project["display_name"])
            new_engine = st.selectbox("Engine", ["godot", "unity", "unreal", "custom"], index=["godot", "unity", "unreal", "custom"].index(project["engine"]))
        with col2:
            new_mode = st.selectbox("Mode", ["development", "design", "prototype", "production"], index=["development", "design", "prototype", "production"].index(project["mode"]))
            new_status = st.selectbox("Status", ["active", "frozen"], index=["active", "frozen"].index(project["status"]))

        config_json = st.text_area("Configuration JSON", value=project["config_json"], height=150)

        submitted = st.form_submit_button("Update Project", type="primary")

        if submitted:
            try:
                update_data = {}
                if new_display_name != project["display_name"]:
                    update_data["display_name"] = new_display_name
                if new_engine != project["engine"]:
                    update_data["engine"] = new_engine
                if new_mode != project["mode"]:
                    update_data["mode"] = new_mode
                if new_status != project["status"]:
                    update_data["status"] = new_status
                if config_json != project["config_json"]:
                    update_data["config_json"] = config_json

                if not update_data:
                    st.info("No changes detected")
                else:
                    patch(f"/api/projects/{project_id}", json=update_data)
                    st.success("Project updated successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
