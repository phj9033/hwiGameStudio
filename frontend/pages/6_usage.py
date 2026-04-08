import streamlit as st
from frontend.api_client import get

st.set_page_config(page_title="Usage & Cost Monitoring", page_icon="💰", layout="wide")

st.title("💰 Usage & Cost Monitoring")

if st.button("🔄 Refresh"):
    st.rerun()

try:
    summary = get("/api/usage/summary")

    st.subheader("Overall Usage")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Input Tokens", f"{summary['total_input_tokens']:,}")
    with col2:
        st.metric("Total Output Tokens", f"{summary['total_output_tokens']:,}")
    with col3:
        st.metric("Total Cost", f"${summary['total_cost']:.4f}")

    st.divider()

    # Usage by project
    st.subheader("Usage by Project")
    projects = get("/api/usage/by-project")
    if not projects:
        st.info("No usage data available yet.")
    else:
        import pandas as pd
        df = pd.DataFrame(projects)[['project_display_name', 'total_input_tokens', 'total_output_tokens', 'total_cost']]
        df.columns = ['Project', 'Input Tokens', 'Output Tokens', 'Cost ($)']
        df['Cost ($)'] = df['Cost ($)'].apply(lambda x: f"${x:.4f}")
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # Usage by agent
    st.subheader("Usage by Agent")
    agents = get("/api/usage/by-agent")
    if not agents:
        st.info("No usage data available yet.")
    else:
        import pandas as pd
        df = pd.DataFrame(agents)[['agent_name', 'total_input_tokens', 'total_output_tokens', 'total_cost']]
        df.columns = ['Agent', 'Input Tokens', 'Output Tokens', 'Cost ($)']
        df['Cost ($)'] = df['Cost ($)'].apply(lambda x: f"${x:.4f}")
        st.dataframe(df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Failed to connect to backend: {e}")
    st.info("Make sure the backend server is running on http://localhost:8000")
