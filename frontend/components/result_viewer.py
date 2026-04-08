import streamlit as st
import requests
from backend.config import BACKEND_URL


def render_result_viewer(agent_run_id: int):
    """
    Component that renders markdown result summary and file path display.

    Args:
        agent_run_id: The ID of the agent run to display results for
    """
    try:
        # Fetch agent run details
        run_response = requests.get(
            f"{BACKEND_URL}/api/runs/{agent_run_id}",
            timeout=5
        )

        if run_response.status_code != 200:
            st.error(f"Failed to fetch agent run details: {run_response.status_code}")
            return

        agent_run = run_response.json()

        # Display result summary if available
        if agent_run.get('result_summary'):
            st.subheader("Result Summary")
            st.markdown(agent_run['result_summary'])
        else:
            st.info("No result summary available yet.")

        # Display result file path and content if available
        if agent_run.get('result_path'):
            st.subheader("Result File")
            st.code(agent_run['result_path'], language=None)

            # Try to fetch and display file content
            if st.button("Load Result File", key=f"load_result_{agent_run_id}"):
                try:
                    result_response = requests.get(
                        f"{BACKEND_URL}/api/runs/{agent_run_id}/result",
                        timeout=10
                    )

                    if result_response.status_code == 200:
                        st.text_area(
                            "File Content",
                            value=result_response.text,
                            height=400,
                            key=f"content_{agent_run_id}"
                        )
                    elif result_response.status_code == 404:
                        st.warning("Result file not found. It may have been moved or deleted.")
                    else:
                        st.error(f"Failed to load result file: {result_response.status_code}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Error loading result file: {e}")
        else:
            st.info("No result file available yet.")

        # Display token usage and cost
        if agent_run.get('input_tokens') or agent_run.get('output_tokens'):
            st.subheader("Usage Statistics")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Input Tokens",
                    f"{agent_run.get('input_tokens', 0):,}",
                    help="Tokens sent to the AI provider"
                )

            with col2:
                st.metric(
                    "Output Tokens",
                    f"{agent_run.get('output_tokens', 0):,}",
                    help="Tokens received from the AI provider"
                )

            with col3:
                cost = agent_run.get('estimated_cost', 0)
                st.metric(
                    "Estimated Cost",
                    f"${cost:.4f}" if cost else "N/A",
                    help="Estimated cost based on token usage"
                )

        # Display timestamps
        if agent_run.get('started_at') or agent_run.get('completed_at'):
            st.subheader("Execution Timeline")
            col1, col2 = st.columns(2)

            with col1:
                if agent_run.get('started_at'):
                    st.text(f"Started: {agent_run['started_at']}")
                else:
                    st.text("Started: Not yet started")

            with col2:
                if agent_run.get('completed_at'):
                    st.text(f"Completed: {agent_run['completed_at']}")
                else:
                    st.text("Completed: In progress")

    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to backend: {e}")
        st.info("Make sure the backend server is running on http://localhost:8000")
