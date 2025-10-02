import streamlit as st
import requests
import uuid
import pandas as pd

# ================== КОНФИГУРАЦИЯ ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 120)

# ================== НАСТРОЙКА СТРАНИЦЫ ==================
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")


# ================== ПАРСИНГ ОТВЕТА N8N ==================
def parse_n8n_response(response_json: list | dict) -> dict:
    try:
        if isinstance(response_json, list) and response_json:
            data = response_json[0]
        else:
            data = response_json

        output_data = data.get('output', {})
        text = output_data.get('analytical_report', 'Ошибка: не удалось извлечь текстовый отчет из ответа.')
        chart = output_data.get('chart_data', None)
        
        return {"text": text, "chart": chart}

    except Exception as e:
        return {"text": f"Критическая ошибка при парсинге ответа: {e}\nСырой ответ: {str(response_json)}", "chart": None}


# ================== ОТПРАВКА ЗАПРОСА К АГЕНТУ ==================
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

    except requests.exceptions.ReadTimeout:
        return {"text": "Ошибка: Время ожидания ответа от сервера истекло.", "chart": None}
    except requests.exceptions.RequestException as e:
        return {"text": f"Ошибка подключения к серверу: {e}", "chart": None}
    except Exception as e:
        return {"text": f"Неожиданная ошибка: {e}", "chart": None}


# ================== UI: БОКОВАЯ ПАНЕЛЬ ==================
with st.sidebar:
    st.subheader("Настройки Агента")
    st.selectbox("Модель", ["Gemini (через n8n)"], disabled=True)
    st.text_area("Системные инструкции", "Ты — полезный аналитический AI-агент...", height=100, disabled=True)
    st.slider("Температура", 0.0, 1.0, 0.7, disabled=True)

    with st.expander("Дополнительные настройки"):
        url_input = st.text_input("Webhook URL", value=N8N_URL)
        debug_mode = st.checkbox("Показывать сырой ответ JSON", value=False)
        st.caption("Команды в чате: `/clear` для очистки, `/newsid` для новой сессии.")


# ================== ИНИЦИАЛИЗАЦИЯ СЕССИИ ЧАТА ==================
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]


# ================== UI: ОТОБРАЖЕНИЕ ИСТОРИИ ЧАТА ==================
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "chart" in message and message["chart"]:
            # --- НАЧАЛО ЗАМЕНЕННОГО БЛОКА 1 ---
            try:
                chart_info = message["chart"]
                if chart_info and chart_info.get('data'):
                    df = pd.DataFrame(chart_info['data'])
                    
                    x_col = chart_info.get('x_column')
                    y_col = chart_info.get('y_column')

                    if not x_col or not y_col:
                        st.error("Ошибка в данных: не указаны имена колонок для осей X и Y.")
                    elif y_col not in df.columns or x_col not in df.columns:
                        st.error(f"Ошибка данных: колонка '{y_col}' или '{x_col}' не найдена.")
                    else:
                        # --- БЛОК ОЧИСТКИ ДАННЫХ ---
                        # 1. Превращаем Y-колонку в строку, чтобы применить текстовые функции
                        clean_series = df[y_col].astype(str)
                        # 2. Убираем все пробелы (например, из "178 970")
                        clean_series = clean_series.str.replace(' ', '', regex=False)
                        # 3. Заменяем запятые на точки для правильной конвертации в число
                        clean_series = clean_series.str.replace(',', '.', regex=False)
                        # 4. Конвертируем очищенную строку в число. Ошибки станут 'NaN'
                        df[y_col] = pd.to_numeric(clean_series, errors='coerce')
                        
                        # Удаляем строки, где конвертация не удалась
                        df.dropna(subset=[y_col], inplace=True)

                        if not df.empty:
                            if chart_info['type'] == 'bar_chart':
                                st.bar_chart(df, x=x_col, y=y_col)
                            elif chart_info['type'] == 'line_chart':
                                st.line_chart(df, x=x_col, y=y_col)
                        else:
                            st.warning("Не удалось построить график: данные не содержат корректных чисел.")
            except Exception as e:
                st.error(f"Не удалось построить график из истории: {e}")
            # --- КОНЕЦ ЗАМЕНЕННОГО БЛОКА 1 ---

# ================== UI: ПОЛЕ ВВОДА И ОБРАБОТКА ЗАПРОСА ==================
if prompt := st.chat_input("Ваш вопрос..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Анализирую данные...")
        
        response_data = ask_agent(prompt, st.session_state.session_id, url_input, debug_mode)
        response_text = response_data.get("text") or "_Пустой ответ от агента_"
        chart_data = response_data.get("chart")
        
        message_placeholder.markdown(response_text)

        if chart_data:
            # --- НАЧАЛО ЗАМЕНЕННОГО БЛОКА 2 ---
            try:
                if chart_data and chart_data.get('data'):
                    df = pd.DataFrame(chart_data['data'])
                    
                    x_col = chart_data.get('x_column')
                    y_col = chart_data.get('y_column')

                    if not x_col or not y_col:
                        st.error("Ошибка в данных от агента: не указаны имена колонок для осей X и Y.")
                    elif y_col not in df.columns or x_col not in df.columns:
                        st.error(f"Ошибка данных: колонка '{y_col}' или '{x_col}' не найдена в ответе агента.")
                    else:
                        # --- БЛОК ОЧИСТКИ ДАННЫХ ---
                        # 1. Превращаем Y-колонку в строку, чтобы применить текстовые функции
                        clean_series = df[y_col].astype(str)
                        # 2. Убираем все пробелы (например, из "178 970")
                        clean_series = clean_series.str.replace(' ', '', regex=False)
                        # 3. Заменяем запятые на точки для правильной конвертации в число
                        clean_series = clean_series.str.replace(',', '.', regex=False)
                        # 4. Конвертируем очищенную строку в число. Ошибки станут 'NaN'
                        df[y_col] = pd.to_numeric(clean_series, errors='coerce')
                        
                        # Удаляем строки, где конвертация не удалась
                        df.dropna(subset=[y_col], inplace=True)

                        if not df.empty:
                            if chart_data['type'] == 'bar_chart':
                                st.bar_chart(df, x=x_col, y=y_col)
                            elif chart_data['type'] == 'line_chart':
                                st.line_chart(df, x=x_col, y=y_col)
                        else:
                            st.warning("Не удалось построить график: данные от агента не содержат корректных чисел.")
            except Exception as e:
                st.error(f"Не удалось построить новый график: {e}")
            # --- КОНЕЦ ЗАМЕНЕННОГО БЛОКА 2 ---

    st.session_state.messages.append({
        "role": "assistant", 
        "content": response_text, 
        "chart": chart_data
    })