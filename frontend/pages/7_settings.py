import streamlit as st
import requests
from backend.config import BACKEND_URL

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")

# Refresh button
if st.button("🔄 Refresh"):
    st.rerun()

# CLI Providers Section
st.subheader("CLI Providers")

try:
    providers_response = requests.get(f"{BACKEND_URL}/api/providers", timeout=5)
    if providers_response.status_code == 200:
        providers = providers_response.json()

        if not providers:
            st.info("No CLI providers configured.")
        else:
            for provider in providers:
                with st.expander(f"{'✅' if provider['enabled'] else '❌'} {provider['name']}", expanded=False):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.text_input(
                            "Command",
                            value=provider['command'],
                            key=f"cmd_{provider['id']}",
                            disabled=True,
                            help="Command to execute for this provider"
                        )

                        st.text_input(
                            "API Key Environment Variable",
                            value=provider['api_key_env'],
                            key=f"env_{provider['id']}",
                            disabled=True,
                            help="Environment variable name for API key"
                        )

                    with col2:
                        enabled = st.checkbox(
                            "Enabled",
                            value=provider['enabled'],
                            key=f"enabled_{provider['id']}"
                        )

                        if st.button("Save Changes", key=f"save_{provider['id']}"):
                            try:
                                update_response = requests.put(
                                    f"{BACKEND_URL}/api/providers/{provider['id']}",
                                    json={"enabled": enabled},
                                    timeout=5
                                )
                                if update_response.status_code == 200:
                                    st.success("Provider updated successfully!")
                                    st.rerun()
                                else:
                                    st.error(f"Error: {update_response.json().get('detail', 'Unknown error')}")
                            except requests.exceptions.RequestException as e:
                                st.error(f"Failed to update provider: {e}")
    else:
        st.error(f"Failed to fetch providers: {providers_response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"Failed to connect to backend: {e}")

st.divider()

# Cost Rates Section
st.subheader("Cost Rates")

try:
    rates_response = requests.get(f"{BACKEND_URL}/api/providers/rates", timeout=5)
    if rates_response.status_code == 200:
        rates = rates_response.json()

        if not rates:
            st.info("No cost rates configured.")
        else:
            for rate in rates:
                with st.expander(f"💰 {rate['provider']} - {rate['model']}", expanded=False):
                    st.caption(f"Last updated: {rate['updated_at']}")

                    col1, col2 = st.columns(2)

                    with col1:
                        input_rate = st.number_input(
                            "Input Rate (per 1K tokens)",
                            value=rate['input_rate'],
                            min_value=0.0,
                            step=0.001,
                            format="%.4f",
                            key=f"input_rate_{rate['id']}",
                            help="Cost per 1,000 input tokens in USD"
                        )

                    with col2:
                        output_rate = st.number_input(
                            "Output Rate (per 1K tokens)",
                            value=rate['output_rate'],
                            min_value=0.0,
                            step=0.001,
                            format="%.4f",
                            key=f"output_rate_{rate['id']}",
                            help="Cost per 1,000 output tokens in USD"
                        )

                    if st.button("Save Changes", key=f"save_rate_{rate['id']}"):
                        try:
                            update_response = requests.put(
                                f"{BACKEND_URL}/api/providers/rates/{rate['id']}",
                                json={
                                    "input_rate": input_rate,
                                    "output_rate": output_rate
                                },
                                timeout=5
                            )
                            if update_response.status_code == 200:
                                st.success("Cost rate updated successfully!")
                                st.rerun()
                            else:
                                st.error(f"Error: {update_response.json().get('detail', 'Unknown error')}")
                        except requests.exceptions.RequestException as e:
                            st.error(f"Failed to update cost rate: {e}")
    else:
        st.error(f"Failed to fetch cost rates: {rates_response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"Failed to connect to backend: {e}")
    st.info("Make sure the backend server is running on http://localhost:8000")
