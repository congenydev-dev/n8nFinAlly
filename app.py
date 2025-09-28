import streamlit as st
import requests
import pandas as pd

N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"

# Приветственный текст, как в вашем примере
st.markdown("©Приветствую. Я ваш Аналитический Интеллектуальный Агент, готовый к обработке. И помните: если будете долго задавать вопрос, не волнуйтесь — я не заржавею, скорее, закодируюсь")
st.divider() # Горизонтальная линия-разделитель для аккуратности

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять?"}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "chart" in message:
            chart_data = pd.DataFrame(message["chart"]["data"])
            if message["chart"]["type"] == "bar_chart":
                st.bar_chart(chart_data, x=chart_data.columns[0], y=chart_data.columns[1])
            elif message["chart"]["type"] == "line_chart":
                st.line_chart(chart_data, x=chart_data.columns[0], y=chart_data.columns[1])

if prompt := st.chat_input("Your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        payload = {"message": prompt}
        with st.spinner('Thinking...'):
            response = requests.post(N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            json_response = response.json()

            text_response = json_response.get("text_response", "Sorry, something went wrong.")
            chart_info = json_response.get("chart_data")

            assistant_message = {"role": "assistant", "content": text_response}
            if chart_info and isinstance(chart_info, dict) and chart_info.get("data"):
                assistant_message["chart"] = chart_info
            
            st.session_state.messages.append(assistant_message)
            
            with st.chat_message("assistant"):
                st.markdown(text_response)
                if chart_info and isinstance(chart_info, dict) and chart_info.get("data"):
                    df = pd.DataFrame(chart_info["data"])
                    chart_type = chart_info.get("type", "bar_chart")
                    
                    if chart_type == "bar_chart":
                        st.bar_chart(df, x=df.columns[0], y=df.columns[1])
                    elif chart_type == "line_chart":
                        st.line_chart(df, x=df.columns[0], y=df.columns[1])

    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to n8n workflow: {e}")