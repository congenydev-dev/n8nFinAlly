import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- Configuration and Helper Functions ---

# Webhook URL is hardcoded for this beta test.
# This is simple and works perfectly for development and testing.
N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"

def display_chart(chart_info: dict):
    """
    Renders an interactive chart using Plotly based on a dictionary.
    """
    try:
        df = pd.DataFrame(chart_info["data"])
        chart_type = chart_info.get("type", "bar_chart")
        
        # Using explicit column names from the JSON response for reliability.
        x_col = chart_info.get("x_column")
        y_col = chart_info.get("y_column")

        # Validate that the necessary column names were provided.
        if not x_col or not y_col:
            st.warning("Server response is missing the required 'x_column' or 'y_column' for the chart.")
            return
            
        title = f"Chart: {y_col} by {x_col}"

        if chart_type == "bar_chart":
            fig = px.bar(df, x=x_col, y=y_col, title=title, template="plotly_white")
        elif chart_type == "line_chart":
            fig = px.line(df, x=x_col, y=y_col, title=title, template="plotly_white", markers=True)
        else:
            st.warning(f"Unknown chart type received: '{chart_type}'")
            return
        
        st.plotly_chart(fig, use_container_width=True)
            
    except Exception as e:
        st.error(f"Failed to display the chart. Error: {e}")

# --- Main Application Logic ---

st.title("Analytical AI Agent")
st.markdown("Hello! I'm your Analytical AI Agent. Ask me to visualize your data.")
st.divider()

# Initialize chat history in session state.
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "What data should we analyze today?"}]

# Display chat history.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "chart" in message:
            display_chart(message["chart"])

# Handle new user input.
if prompt := st.chat_input("Ask something about your data..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.spinner('Analyzing...'):
            response = requests.post(N8N_WEBHOOK_URL, json={"message": prompt})
            response.raise_for_status()
            json_response = response.json()

        text_response = json_response.get("text_response", "Received an empty response from the server.")
        chart_info = json_response.get("chart_data")
        
        assistant_message = {"role": "assistant", "content": text_response}
        if isinstance(chart_info, dict) and chart_info.get("data"):
            assistant_message["chart"] = chart_info
        
        st.session_state.messages.append(assistant_message)
        
        with st.chat_message("assistant"):
            st.markdown(text_response)
            if "chart" in assistant_message:
                display_chart(assistant_message["chart"])

    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to the workflow: {e}")
    except requests.exceptions.JSONDecodeError:
        st.error("Failed to process the server's response. It was not valid JSON.")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")