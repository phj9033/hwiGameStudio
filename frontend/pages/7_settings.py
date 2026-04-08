import streamlit as st
from frontend.api_client import get, put

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
                col1, col2 = st.columns(2)
                with col1:
                    st.text_input("Command", value=provider['command'], key=f"cmd_{provider['id']}", disabled=True)
                    st.text_input("API Key Env Var", value=provider['api_key_env'], key=f"env_{provider['id']}", disabled=True)
                with col2:
                    enabled = st.checkbox("Enabled", value=provider['enabled'], key=f"enabled_{provider['id']}")
                    if st.button("Save Changes", key=f"save_{provider['id']}"):
                        try:
                            put(f"/api/providers/{provider['id']}", json={"enabled": enabled})
                            st.success("Provider updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")
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
