import streamlit as st
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from api_client import get, put, post

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")

if st.button("🔄 Refresh"):
    st.rerun()

# CLI Providers Section
st.subheader("CLI Providers")

try:
    providers = get("/api/providers")

    if not providers:
        st.info("No CLI providers configured.")
    else:
        for provider in providers:
            with st.expander(f"{'✅' if provider['enabled'] else '❌'} {provider['name']}", expanded=False):
                command = st.text_input("Command", value=provider['command'], key=f"cmd_{provider['id']}")
                enabled = st.checkbox("Enabled", value=provider['enabled'], key=f"enabled_{provider['id']}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Save Changes", key=f"save_{provider['id']}", type="primary"):
                        try:
                            update_data = {"enabled": enabled}
                            if command != provider['command']:
                                update_data["command"] = command
                            put(f"/api/providers/{provider['id']}", json=update_data)
                            st.success("Provider updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")
                with col2:
                    if st.button("Test Connection", key=f"test_{provider['id']}"):
                        with st.spinner("Testing..."):
                            try:
                                result = post(f"/api/providers/{provider['id']}/test")
                                if result.get("success"):
                                    st.success(f"OK: {result['message']}")
                                else:
                                    st.error(f"Failed: {result['message']}")
                            except Exception as e:
                                st.error(f"Test failed: {e}")
except Exception as e:
    st.error(f"Failed to connect to backend: {e}")

st.divider()

# Cost Rates Section
st.subheader("Cost Rates")

try:
    rates = get("/api/providers/rates")

    if not rates:
        st.info("No cost rates configured.")
    else:
        for rate in rates:
            with st.expander(f"💰 {rate['provider']} - {rate['model']}", expanded=False):
                st.caption(f"Last updated: {rate['updated_at']}")
                col1, col2 = st.columns(2)
                with col1:
                    input_rate = st.number_input("Input Rate (per 1K tokens)", value=rate['input_rate'], min_value=0.0, step=0.001, format="%.4f", key=f"input_rate_{rate['id']}")
                with col2:
                    output_rate = st.number_input("Output Rate (per 1K tokens)", value=rate['output_rate'], min_value=0.0, step=0.001, format="%.4f", key=f"output_rate_{rate['id']}")
                if st.button("Save Changes", key=f"save_rate_{rate['id']}"):
                    try:
                        put(f"/api/providers/rates/{rate['id']}", json={"input_rate": input_rate, "output_rate": output_rate})
                        st.success("Cost rate updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
except Exception as e:
    st.error(f"Failed to connect to backend: {e}")
