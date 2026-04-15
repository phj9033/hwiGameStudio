import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get

st.set_page_config(page_title="Usage Monitoring", page_icon="📊", layout="wide")

st.title("📊 Usage Monitoring")

tab_studio, tab_ccusage = st.tabs(["🏭 Studio Usage", "📈 Overall Usage (ccusage)"])

# --- Tab 1: Studio Usage ---
with tab_studio:
    if st.button("🔄 Refresh", key="refresh_studio"):
        st.rerun()

    try:
        summary = get("/api/usage/summary")

        st.subheader("Overall Studio Usage")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Input Tokens", f"{summary['total_input_tokens']:,}")
        with col2:
            st.metric("Total Output Tokens", f"{summary['total_output_tokens']:,}")

        st.divider()

        # Usage by project
        st.subheader("Usage by Project")
        projects = get("/api/usage/by-project")
        if not projects:
            st.info("No usage data available yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(projects)[['project_display_name', 'total_input_tokens', 'total_output_tokens']]
            df.columns = ['Project', 'Input Tokens', 'Output Tokens']
            df['Input Tokens'] = df['Input Tokens'].apply(lambda x: f"{x:,}")
            df['Output Tokens'] = df['Output Tokens'].apply(lambda x: f"{x:,}")
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()

        # Usage by agent
        st.subheader("Usage by Agent")
        agents = get("/api/usage/by-agent")
        if not agents:
            st.info("No usage data available yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(agents)[['agent_name', 'total_input_tokens', 'total_output_tokens']]
            df.columns = ['Agent', 'Input Tokens', 'Output Tokens']
            df['Input Tokens'] = df['Input Tokens'].apply(lambda x: f"{x:,}")
            df['Output Tokens'] = df['Output Tokens'].apply(lambda x: f"{x:,}")
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
        st.info("Make sure the backend server is running on http://localhost:8000")


# --- Tab 2: Overall Usage (ccusage) ---
with tab_ccusage:
    col_refresh, col_period = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh", key="refresh_ccusage"):
            st.rerun()
    with col_period:
        period = st.selectbox("Period", ["daily", "weekly", "monthly"], index=0)

    try:
        result = get(f"/api/ccusage?period={period}")

        if not result.get("success"):
            st.error(result.get("error", "Unknown error"))
            st.warning(result.get("help", ""))
            st.code("npx ccusage@latest", language="bash")
            st.stop()

        data = result["data"]
        totals = data.get("totals", {})

        # Summary metrics
        st.subheader("Total Usage")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Cost", f"${totals.get('totalCost', 0):.2f}")
        with col2:
            st.metric("Input Tokens", f"{totals.get('inputTokens', 0):,}")
        with col3:
            st.metric("Output Tokens", f"{totals.get('outputTokens', 0):,}")
        with col4:
            total_cache = totals.get('cacheCreationTokens', 0) + totals.get('cacheReadTokens', 0)
            st.metric("Cache Tokens", f"{total_cache:,}")

        st.divider()

        # Period breakdown
        period_key = period  # daily, weekly, monthly
        rows = data.get(period_key, [])
        if not rows:
            st.info("No usage data for this period.")
        else:
            import pandas as pd

            st.subheader(f"{period.capitalize()} Breakdown")
            date_col = "date" if period == "daily" else ("week" if period == "weekly" else "month")
            df_data = []
            for row in rows:
                df_data.append({
                    "Date": row.get(date_col, row.get("date", "?")),
                    "Input": f"{row.get('inputTokens', 0):,}",
                    "Output": f"{row.get('outputTokens', 0):,}",
                    "Cache Create": f"{row.get('cacheCreationTokens', 0):,}",
                    "Cache Read": f"{row.get('cacheReadTokens', 0):,}",
                    "Cost": f"${row.get('totalCost', 0):.2f}",
                    "Models": ", ".join(row.get("modelsUsed", [])),
                })
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Model breakdown (expandable)
            st.subheader("Model Breakdown")
            for row in rows:
                date_val = row.get(date_col, row.get("date", "?"))
                breakdowns = row.get("modelBreakdowns", [])
                if breakdowns:
                    with st.expander(f"📅 {date_val} — ${row.get('totalCost', 0):.2f}"):
                        bd_data = []
                        for bd in breakdowns:
                            bd_data.append({
                                "Model": bd.get("modelName", "?"),
                                "Input": f"{bd.get('inputTokens', 0):,}",
                                "Output": f"{bd.get('outputTokens', 0):,}",
                                "Cache Create": f"{bd.get('cacheCreationTokens', 0):,}",
                                "Cache Read": f"{bd.get('cacheReadTokens', 0):,}",
                                "Cost": f"${bd.get('cost', 0):.2f}",
                            })
                        st.dataframe(pd.DataFrame(bd_data), use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Failed to load ccusage data: {e}")
        st.info("Make sure the backend server is running on http://localhost:8000")
