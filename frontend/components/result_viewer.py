import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, get_text
from datetime import datetime


def render_session_viewer(session_id: int):
    """Component that renders session details, log, workspace documents, and usage stats."""
    try:
        session = get(f"/api/sessions/{session_id}")

        # Session status and basic info
        status = session.get("status", "unknown")
        status_config = {
            "pending": {"icon": "⏳", "color": "#808080", "label": "Pending"},
            "waiting": {"icon": "⏸️", "color": "#FFA500", "label": "Waiting"},
            "running": {"icon": "▶️", "color": "#1E90FF", "label": "Running"},
            "completed": {"icon": "✅", "color": "#32CD32", "label": "Completed"},
            "failed": {"icon": "❌", "color": "#DC143C", "label": "Failed"},
            "cancelled": {"icon": "⏹️", "color": "#808080", "label": "Cancelled"}
        }
        config = status_config.get(status, {"icon": "❓", "color": "#808080", "label": status})

        st.markdown(
            f"<span style='background-color:{config['color']};color:white;padding:8px 12px;border-radius:4px;font-size:14px;font-weight:bold;'>"
            f"{config['icon']} {config['label']}</span>",
            unsafe_allow_html=True
        )
        st.markdown("")

        # Basic information
        st.subheader("Session Information")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Agent:** {session.get('agent_name', 'Unknown')}")
            st.markdown(f"**Provider:** {session.get('cli_provider', 'Unknown')}")
        with col2:
            if session.get("depends_on"):
                st.markdown(f"**Depends on:** {', '.join(session['depends_on'])}")
            if session.get("produces"):
                st.markdown(f"**Produces:** {', '.join(session['produces'])}")

        if session.get("instruction"):
            st.markdown(f"**Instruction:** {session['instruction']}")

        # Timeline information
        if session.get("started_at") or session.get("completed_at"):
            st.subheader("Execution Timeline")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.text(f"Started: {session.get('started_at', 'Not yet started')}")
            with col2:
                st.text(f"Completed: {session.get('completed_at', 'In progress' if status == 'running' else 'N/A')}")
            with col3:
                if session.get("started_at") and session.get("completed_at"):
                    try:
                        started = datetime.fromisoformat(session["started_at"])
                        completed = datetime.fromisoformat(session["completed_at"])
                        duration = completed - started
                        mins, secs = divmod(int(duration.total_seconds()), 60)
                        st.text(f"Duration: {mins}m {secs}s")
                    except Exception:
                        pass

        # Token usage
        if session.get("input_tokens") or session.get("output_tokens"):
            st.subheader("Usage Statistics")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Input Tokens", f"{session.get('input_tokens', 0):,}")
            with col2:
                st.metric("Output Tokens", f"{session.get('output_tokens', 0):,}")
            with col3:
                total = session.get('input_tokens', 0) + session.get('output_tokens', 0)
                st.metric("Total Tokens", f"{total:,}")

        # Error message for failed sessions
        if status == "failed" and session.get("error_message"):
            st.subheader("Error Details")
            st.error(session["error_message"])

        # Session log
        st.subheader("Session Log")
        try:
            log_content = get_text(f"/api/sessions/{session_id}/log")
            if log_content and log_content.strip():
                st.markdown(log_content)
            else:
                st.info("No log content available yet.")
        except Exception as e:
            st.warning(f"Could not load session log: {e}")

        # Workspace documents
        if session.get("produces"):
            st.subheader("Workspace Documents")
            try:
                ticket_id = session.get("ticket_id")
                if ticket_id:
                    workspace = get(f"/api/tickets/{ticket_id}/workspace")
                    documents = workspace.get("documents", [])

                    # Filter documents produced by this session
                    session_docs = [doc for doc in documents if doc.get("artifact_name") in session.get("produces", [])]

                    if session_docs:
                        for doc in session_docs:
                            with st.expander(f"📄 {doc['artifact_name']}", expanded=False):
                                st.markdown(f"**Path:** `{doc['path']}`")
                                st.markdown(f"**Created:** {doc.get('created_at', 'Unknown')}")
                                if doc.get("content_preview"):
                                    st.markdown("**Preview:**")
                                    st.code(doc["content_preview"], language=doc.get("language", "text"))
                    else:
                        st.info("No documents produced by this session yet.")
                else:
                    st.info("Ticket ID not available.")
            except Exception as e:
                st.warning(f"Could not load workspace documents: {e}")

    except Exception as e:
        st.error(f"Failed to fetch session details: {e}")


# Legacy function for backward compatibility
def render_result_viewer(agent_run_id: int):
    """DEPRECATED: Legacy component that renders markdown result summary and file path display.
    This function is kept for backward compatibility but should not be used for new code.
    Use render_session_viewer() instead for session-based architecture.
    """
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
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Input Tokens", f"{agent_run.get('input_tokens', 0):,}")
            with col2:
                st.metric("Output Tokens", f"{agent_run.get('output_tokens', 0):,}")

        if agent_run.get('started_at') or agent_run.get('completed_at'):
            st.subheader("Execution Timeline")
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"Started: {agent_run.get('started_at', 'Not yet started')}")
            with col2:
                st.text(f"Completed: {agent_run.get('completed_at', 'In progress')}")

    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
