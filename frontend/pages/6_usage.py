import streamlit as st
import requests
from backend.config import BACKEND_URL

st.set_page_config(page_title="Usage & Cost Monitoring", page_icon="💰", layout="wide")

st.title("💰 Usage & Cost Monitoring")

# Refresh button
if st.button("🔄 Refresh"):
    st.rerun()

# Fetch usage summary
try:
    summary_response = requests.get(f"{BACKEND_URL}/api/usage/summary", timeout=5)
    if summary_response.status_code == 200:
        summary = summary_response.json()

        # Display summary metrics
        st.subheader("Overall Usage")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Total Input Tokens",
                f"{summary['total_input_tokens']:,}",
                help="Total tokens sent to AI providers"
            )

        with col2:
            st.metric(
                "Total Output Tokens",
                f"{summary['total_output_tokens']:,}",
                help="Total tokens received from AI providers"
            )

        with col3:
            st.metric(
                "Total Cost",
                f"${summary['total_cost']:.4f}",
                help="Total estimated cost across all runs"
            )

        st.divider()

        # Usage by project
        st.subheader("Usage by Project")
        project_response = requests.get(f"{BACKEND_URL}/api/usage/by-project", timeout=5)
        if project_response.status_code == 200:
            projects = project_response.json()

            if not projects:
                st.info("No usage data available yet.")
            else:
                # Create a table
                import pandas as pd
                df_projects = pd.DataFrame(projects)
                df_projects = df_projects[[
                    'project_display_name',
                    'total_input_tokens',
                    'total_output_tokens',
                    'total_cost'
                ]]
                df_projects.columns = ['Project', 'Input Tokens', 'Output Tokens', 'Cost ($)']
                df_projects['Cost ($)'] = df_projects['Cost ($)'].apply(lambda x: f"${x:.4f}")

                st.dataframe(
                    df_projects,
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.error(f"Failed to fetch project usage: {project_response.status_code}")

        st.divider()

        # Usage by agent
        st.subheader("Usage by Agent")
        agent_response = requests.get(f"{BACKEND_URL}/api/usage/by-agent", timeout=5)
        if agent_response.status_code == 200:
            agents = agent_response.json()

            if not agents:
                st.info("No usage data available yet.")
            else:
                # Create a table
                import pandas as pd
                df_agents = pd.DataFrame(agents)
                df_agents = df_agents[[
                    'agent_name',
                    'total_input_tokens',
                    'total_output_tokens',
                    'total_cost'
                ]]
                df_agents.columns = ['Agent', 'Input Tokens', 'Output Tokens', 'Cost ($)']
                df_agents['Cost ($)'] = df_agents['Cost ($)'].apply(lambda x: f"${x:.4f}")

                st.dataframe(
                    df_agents,
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.error(f"Failed to fetch agent usage: {agent_response.status_code}")
    else:
        st.error(f"Failed to fetch usage summary: {summary_response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"Failed to connect to backend: {e}")
    st.info("Make sure the backend server is running on http://localhost:8000")
