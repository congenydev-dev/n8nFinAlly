import streamlit as st
import requests
import uuid
import pandas as pd

# ================== КОНФИГУРАЦИЯ ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 120)

# ================== НАСТРОЙКА СТРАНИЦЫ ==================
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")

# ================== ФУНКЦИИ ==================
def parse_n8n_response(response_json: list | dict) -> dict:
    try:
        data = response_json[0] if isinstance(response_json, list) and response_json else response_json
        output_data = data.get('output', {})
        text = output_data.get('analytical_report', 'Ошибка: не удалось извлечь текстовый отчет из ответа.')
        chart = output_data.get('chart_data', None)
        return {"text": text, "chart": chart}
    except Exception as e:
        return {"text": f"Критическая ошибка при парсинге ответа: {e}\nСырой ответ: {str(response_json)}", "chart": None}

def ask_agent(prompt: str, session_id: str, url: str, debug: bool) -> dict:
    headers = {"x-session-id": session_id}
    payload = {"prompt": prompt, "sessionId": session_id}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        raw_response = response.json()
        if debug:
            st.sidebar.json(raw_response)
        return parse_n8n_response(raw_response)
    except requests.exceptions.RequestException as e:
        return {"text": f"Ошибка подключения или таймаута: {e}", "chart": None}
    except Exception as e:
        return {"text": f"Неожиданная ошибка: {e}", "chart": None}

def display_chart(chart_info):
    """Функция для очистки данных и отображения графика."""
    try:
        if chart_info and chart_info.get('data'):
            df = pd.DataFrame(chart_info['data'])
            x_col, y_col = chart_info.get('x_column'), chart_info.get('y_column')

            if not all([x_col, y_col, x_col in df.columns, y_col in df.columns]):
                st.error("Ошибка в структуре данных для графика.")
                return

            df[y_col] = df[y_col].astype(str).str.replace(' ', '', regex=False).str.replace(',', '.', regex=False)
            df[y_col] = pd.to_numeric(df[y_col], errors='coerce')
            df.dropna(subset=[y_col], inplace=True)

            if not df.empty:
                df = df.set_index(x_col)
                chart_type = chart_info.get('type')
                if chart_type == 'bar_chart':
                    st.bar_chart(df[[y_col]])
                elif chart_type == 'line_chart':
                    st.line_chart(df[[y_col]])
            else:
                st.warning("Данные для графика оказались пустыми после очистки.")
    except Exception as e:
        st.error(f"Не удалось построить график: {e}")

# ================== UI БОКОВАЯ ПАНЕЛЬ ==================
with st.sidebar:
    st.subheader("Настройки Агента")
    # ... (остальной код боковой панели без изменений) ...
    st.selectbox("Модель", ["Gemini (через n8n)"], disabled=True)
    st.text_area("Системные инструкции", "Ты — полезный аналитический AI-агент...", height=100, disabled=True)
    st.slider("Температура", 0.0, 1.0, 0.7, disabled=True)
    with st.expander("Дополнительные настройки"):
        url_input = st.text_input("Webhook URL", value=N8N_URL)
        debug_mode = st.checkbox("Показывать сырой ответ JSON", value=False)
        st.caption("Команды в чате: `/clear` для очистки.")

# ================== ИНИЦИАЛИЗАЦИЯ И ИСТОРИЯ ЧАТА ==================
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "chart" in msg and msg.get("chart"):
            display_chart(msg["chart"])

# ================== ОБРАБОТКА НОВОГО ЗАПРОСА ==================
if prompt := st.chat_input("Ваш вопрос..."):
    if prompt == "/clear":
        st.session_state.messages = [{"role": "assistant", "content": "История чата очищена."}]
        st.rerun()
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)

        with st.chat_message("assistant"):
            # --- НАЧАЛО ИСПРАВЛЕННОГО БЛОКА ---
            # Используем st.spinner для отображения сообщения о загрузке.
            # Это надежнее, чем st.empty().
            with st.spinner("Анализирую данные..."):
                response_data = ask_agent(prompt, st.session_state.get("session_id", "default"), url_input, debug_mode)
            
            # После завершения spinner'а, просто выводим результаты.
            response_text = response_data.get("text", "_Пустой ответ от агента_")
            chart_data = response_data.get("chart")

            st.markdown(response_text)
            if chart_data:
                display_chart(chart_data)
            # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---

        # Добавляем полное сообщение в историю для будущих перерисовок
        st.session_state.messages.append({"role": "assistant", "content": response_text, "chart": chart_data})