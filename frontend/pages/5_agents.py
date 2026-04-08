import streamlit as st
import requests
from backend.config import BACKEND_URL

st.set_page_config(page_title="Agent Management", page_icon="🤖", layout="wide")

st.title("🤖 Agent Management")

# Fetch agents
try:
    response = requests.get(f"{BACKEND_URL}/api/agents", timeout=5)
    if response.status_code == 200:
        agents = response.json()
    else:
        agents = []
        st.error(f"Failed to fetch agents: {response.status_code}")
except requests.exceptions.RequestException as e:
    agents = []
    st.error(f"Failed to connect to backend: {e}")

if not agents:
    st.info("No agents found. Create .md files in the agents directory to get started.")
else:
    # Agent selector
    col1, col2 = st.columns([3, 1])

    with col1:
        selected_agent = st.selectbox(
            "Select Agent",
            options=[a["name"] for a in agents],
            format_func=lambda x: x.replace("_", " ").title()
        )

    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    if selected_agent:
        st.divider()

        # Create tabs for editor and run history
        tab1, tab2 = st.tabs(["📝 Editor", "📊 Run History"])

        with tab1:
            # Fetch agent content
            try:
                response = requests.get(f"{BACKEND_URL}/api/agents/{selected_agent}", timeout=5)
                if response.status_code == 200:
                    agent_data = response.json()
                    current_content = agent_data["content"]

                    st.subheader(f"Editing: {selected_agent.replace('_', ' ').title()}")

                    # Markdown editor
                    new_content = st.text_area(
                        "Agent Instructions (Markdown)",
                        value=current_content,
                        height=400,
                        help="Edit the agent's instruction markdown file"
                    )

                    col1, col2 = st.columns([1, 5])
                    with col1:
                        if st.button("💾 Save Changes", type="primary"):
                            try:
                                update_response = requests.put(
                                    f"{BACKEND_URL}/api/agents/{selected_agent}",
                                    json={"content": new_content},
                                    timeout=5
                                )
                                if update_response.status_code == 200:
                                    st.success("✅ Agent instructions updated successfully!")
                                    st.rerun()
                                else:
                                    st.error(f"Failed to update: {update_response.json().get('detail', 'Unknown error')}")
                            except requests.exceptions.RequestException as e:
                                st.error(f"Failed to save: {e}")

                    with col2:
                        if new_content != current_content:
                            st.warning("⚠️ You have unsaved changes")

                    st.divider()

                    # Preview
                    with st.expander("👁️ Preview", expanded=False):
                        st.markdown(new_content)

                else:
                    st.error(f"Failed to load agent: {response.status_code}")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to backend: {e}")

        with tab2:
            st.subheader(f"Run History: {selected_agent.replace('_', ' ').title()}")

            # Fetch run history
            try:
                response = requests.get(
                    f"{BACKEND_URL}/api/agents/{selected_agent}/runs",
                    params={"page": 1, "per_page": 50},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    runs = data.get("items", [])
                    total = data.get("total", 0)

                    if total == 0:
                        st.info("No runs found for this agent yet.")
                    else:
                        st.caption(f"Showing {len(runs)} of {total} runs")

                        # Display runs
                        for run in runs:
                            with st.container():
                                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])

                                with col1:
                                    status_icon = {
                                        "pending": "⏳",
                                        "running": "▶️",
                                        "completed": "✅",
                                        "failed": "❌",
                                        "cancelled": "⏹️"
                                    }.get(run["status"], "❓")
                                    st.markdown(f"**{status_icon} Run #{run['id']}**")
                                    st.caption(f"Provider: {run['cli_provider']}")

                                with col2:
                                    if run["started_at"]:
                                        st.caption(f"Started: {run['started_at'][:19]}")

                                with col3:
                                    if run.get("input_tokens"):
                                        st.metric("Input Tokens", f"{run['input_tokens']:,}")
                                    if run.get("output_tokens"):
                                        st.metric("Output Tokens", f"{run['output_tokens']:,}")

                                with col4:
                                    if run.get("estimated_cost"):
                                        st.metric("Cost", f"${run['estimated_cost']:.4f}")

                                # Show instruction if available
                                if run.get("instruction"):
                                    with st.expander("View Instruction"):
                                        st.text(run["instruction"])

                                # Show result if available
                                if run.get("result_summary"):
                                    with st.expander("View Result"):
                                        st.text(run["result_summary"])
                                        if run.get("result_path"):
                                            st.caption(f"Output: {run['result_path']}")

                                st.divider()
                else:
                    st.error(f"Failed to fetch runs: {response.status_code}")
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to backend: {e}")
