import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- Конфигурация ---
# Вставляем ваш рабочий URL от AI-агента
N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/12233d88-06cd-43cf-80f5-dacf042d14e6"

def display_chart(chart_info: dict):
    """Отображает интерактивный график Plotly на основе словаря."""
    try:
        df = pd.DataFrame(chart_info["data"])
        chart_type = chart_info.get("type", "bar_chart")
        
        x_col = chart_info.get("x_column")
        y_col = chart_info.get("y_column")

        if not x_col or not y_col:
            st.warning("Ответ от сервера не содержит обязательные поля 'x_column' или 'y_column' для графика.")
            return
            
        title = f"График: {y_col} по {x_col}"

        if chart_type == "bar_chart":
            fig = px.bar(df, x=x_col, y=y_col, title=title, template="plotly_white")
        elif chart_type == "line_chart":
            fig = px.line(df, x=x_col, y=y_col, title=title, template="plotly_white", markers=True)
        else:
            st.warning(f"Получен неизвестный тип графика: '{chart_type}'")
            return
        
        st.plotly_chart(fig, use_container_width=True)
            
    except Exception as e:
        st.error(f"Не удалось отобразить график. Ошибка: {e}")

# --- Основная логика приложения ---

st.title("Аналитический AI-агент")
st.markdown("Здравствуйте! Я ваш аналитический AI-агент. Попросите меня визуализировать данные.")
st.divider()

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Какие данные проанализируем сегодня?"}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "chart" in message:
            display_chart(message["chart"])

if prompt := st.chat_input("Спросите что-нибудь о ваших данных..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.spinner('Анализирую...'):
            # Важно: отправляем ключ 'prompt', как мы настроили в n8n
            response = requests.post(N8N_WEBHOOK_URL, json={"prompt": prompt})
            response.raise_for_status()
            json_response = response.json()

        # Streamlit ожидает два ключа: 'text_response' и 'chart_data'
        text_response = json_response.get("text_response", "Получен пустой ответ от сервера.")
        chart_info = json_response.get("chart_data")
        
        assistant_message = {"role": "assistant", "content": text_response}
        # Проверяем, что chart_info это словарь и в нем есть данные
        if isinstance(chart_info, dict) and chart_info.get("data"):
            assistant_message["chart"] = chart_info
        
        st.session_state.messages.append(assistant_message)
        
        with st.chat_message("assistant"):
            st.markdown(text_response)
            if "chart" in assistant_message:
                display_chart(assistant_message["chart"])

    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка подключения к workflow: {e}")
    except requests.exceptions.JSONDecodeError:
        st.error("Не удалось обработать ответ сервера. Ответ не является валидным JSON.")
    except Exception as e:
        st.error(f"Произошла непредвиденная ошибка: {e}")