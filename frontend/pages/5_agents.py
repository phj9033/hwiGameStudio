import streamlit as st
from frontend.api_client import get, put

st.set_page_config(page_title="Agent Management", page_icon="🤖", layout="wide")

st.title("🤖 Agent Management")

# Fetch agents
try:
    agents = get("/api/agents")
except Exception as e:
    agents = []
    st.error(f"Failed to connect to backend: {e}")

if not agents:
    st.info("No agents found. Create .md files in the agents directory to get started.")
else:
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
        tab1, tab2 = st.tabs(["📝 Editor", "📊 Run History"])

        with tab1:
            try:
                agent_data = get(f"/api/agents/{selected_agent}")
                current_content = agent_data["content"]

                st.subheader(f"Editing: {selected_agent.replace('_', ' ').title()}")
                new_content = st.text_area("Agent Instructions (Markdown)", value=current_content, height=400)

                col1, col2 = st.columns([1, 5])
                with col1:
                    if st.button("💾 Save Changes", type="primary"):
                        try:
                            put(f"/api/agents/{selected_agent}", json={"content": new_content})
                            st.success("✅ Agent instructions updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save: {e}")
                with col2:
                    if new_content != current_content:
                        st.warning("⚠️ You have unsaved changes")

                with st.expander("👁️ Preview", expanded=False):
                    st.markdown(new_content)

            except Exception as e:
                st.error(f"Failed to load agent: {e}")

        with tab2:
            st.subheader(f"Run History: {selected_agent.replace('_', ' ').title()}")
            try:
                data = get(f"/api/agents/{selected_agent}/runs", params={"page": 1, "per_page": 50})
                runs = data.get("items", [])
                total = data.get("total", 0)

                if total == 0:
                    st.info("No runs found for this agent yet.")
                else:
                    st.caption(f"Showing {len(runs)} of {total} runs")
                    for run in runs:
                        with st.container():
                            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                            with col1:
                                status_icon = {"pending": "⏳", "running": "▶️", "completed": "✅", "failed": "❌", "cancelled": "⏹️"}.get(run["status"], "❓")
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
                            if run.get("instruction"):
                                with st.expander("View Instruction"):
                                    st.text(run["instruction"])
                            if run.get("result_summary"):
                                with st.expander("View Result"):
                                    st.text(run["result_summary"])
                            st.divider()
            except Exception as e:
                st.error(f"Failed to fetch runs: {e}")
