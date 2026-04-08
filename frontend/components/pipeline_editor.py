import streamlit as st
from typing import List, Dict


def pipeline_editor():
    """Pipeline editor component for building step/agent workflows"""

    # Initialize session state for steps
    if "pipeline_steps" not in st.session_state:
        st.session_state.pipeline_steps = []

    st.subheader("Pipeline Configuration")

    # Add step button
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("+ Add Step", type="primary"):
            st.session_state.pipeline_steps.append({
                "step_order": len(st.session_state.pipeline_steps) + 1,
                "agents": []
            })
            st.rerun()

    with col2:
        if st.button("Clear All"):
            st.session_state.pipeline_steps = []
            st.rerun()

    if not st.session_state.pipeline_steps:
        st.info("No steps defined. Click 'Add Step' to start building your pipeline.")
        return []

    # Display and edit steps
    for step_idx, step in enumerate(st.session_state.pipeline_steps):
        with st.expander(f"Step {step['step_order']}", expanded=True):
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("Remove Step", key=f"remove_step_{step_idx}"):
                    st.session_state.pipeline_steps.pop(step_idx)
                    # Reorder remaining steps
                    for i, s in enumerate(st.session_state.pipeline_steps):
                        s["step_order"] = i + 1
                    st.rerun()

            # Agent list for this step
            st.markdown("**Agents:**")

            # Add agent button
            if st.button(f"+ Add Agent", key=f"add_agent_{step_idx}"):
                step["agents"].append({
                    "agent_name": "",
                    "cli_provider": "claude",
                    "instruction": "",
                    "context_refs": []
                })
                st.rerun()

            # Display agents
            if not step["agents"]:
                st.caption("No agents in this step")
            else:
                for agent_idx, agent in enumerate(step["agents"]):
                    with st.container():
                        col1, col2, col3 = st.columns([2, 2, 1])

                        with col1:
                            agent["agent_name"] = st.text_input(
                                "Agent Name",
                                value=agent.get("agent_name", ""),
                                key=f"agent_name_{step_idx}_{agent_idx}",
                                placeholder="e.g., sr_game_designer"
                            )

                        with col2:
                            agent["cli_provider"] = st.selectbox(
                                "CLI Provider",
                                ["claude", "codex"],
                                index=0 if agent.get("cli_provider") == "claude" else 1,
                                key=f"provider_{step_idx}_{agent_idx}"
                            )

                        with col3:
                            if st.button("Remove", key=f"remove_agent_{step_idx}_{agent_idx}"):
                                step["agents"].pop(agent_idx)
                                st.rerun()

                        agent["instruction"] = st.text_area(
                            "Instruction",
                            value=agent.get("instruction", ""),
                            key=f"instruction_{step_idx}_{agent_idx}",
                            placeholder="What should this agent do?",
                            height=100
                        )

                        st.divider()

    return st.session_state.pipeline_steps


def validate_pipeline(steps: List[Dict]) -> tuple[bool, str]:
    """Validate pipeline configuration"""
    if not steps:
        return False, "Pipeline must have at least one step"

    for step_idx, step in enumerate(steps):
        if not step.get("agents"):
            return False, f"Step {step_idx + 1} must have at least one agent"

        for agent_idx, agent in enumerate(step["agents"]):
            if not agent.get("agent_name"):
                return False, f"Agent {agent_idx + 1} in Step {step_idx + 1} must have a name"

    return True, ""
