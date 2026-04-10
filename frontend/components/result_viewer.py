import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, get_text


def render_result_viewer(agent_run_id: int):
    """Component that renders markdown result summary and file path display."""
    try:
        agent_run = get(f"/api/runs/{agent_run_id}")

        if agent_run.get('result_summary'):
            st.subheader("Result Summary")
            st.markdown(agent_run['result_summary'])
        else:
            st.info("No result summary available yet.")

        if agent_run.get('result_path'):
            st.subheader("Result File")
            st.code(agent_run['result_path'], language=None)

            if st.button("Load Result File", key=f"load_result_{agent_run_id}"):
                try:
                    content = get_text(f"/api/runs/{agent_run_id}/result")
                    st.text_area("File Content", value=content, height=400, key=f"content_{agent_run_id}")
                except Exception as e:
                    st.warning(f"Could not load result file: {e}")
        else:
            st.info("No result file available yet.")

        if agent_run.get('input_tokens') or agent_run.get('output_tokens'):
            st.subheader("Usage Statistics")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Input Tokens", f"{agent_run.get('input_tokens', 0):,}")
            with col2:
                st.metric("Output Tokens", f"{agent_run.get('output_tokens', 0):,}")
            with col3:
                cost = agent_run.get('estimated_cost', 0)
                st.metric("Estimated Cost", f"${cost:.4f}" if cost else "N/A")

        if agent_run.get('started_at') or agent_run.get('completed_at'):
            st.subheader("Execution Timeline")
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"Started: {agent_run.get('started_at', 'Not yet started')}")
            with col2:
                st.text(f"Completed: {agent_run.get('completed_at', 'In progress')}")

    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
