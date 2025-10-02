import streamlit as st
import requests
import uuid
import pandas as pd

# ================== КОНФИГУРАЦИЯ (без изменений) ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 120)

# ================== НАСТРОЙКА СТРАНИЦЫ (без изменений) ==================
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")


# ================== ФУНКЦИИ (без изменений) ==================
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

# ================== UI БОКОВАЯ ПАНЕЛЬ (без изменений) ==================
with st.sidebar:
    st.subheader("Настройки Агента")
    st.selectbox("Модель", ["Gemini (через n8n)"], disabled=True)
    st.text_area("Системные инструкции", "Ты — полезный аналитический AI-агент...", height=100, disabled=True)
    st.slider("Температура", 0.0, 1.0, 0.7, disabled=True)
    with st.expander("Дополнительные настройки"):
        url_input = st.text_input("Webhook URL", value=N8N_URL)
        debug_mode = st.checkbox("Показывать сырой ответ JSON", value=False)
        st.caption("Команды в чате: `/clear` для очистки, `/newsid` для новой сессии.")

# ================== ИНИЦИАЛИЗАЦИЯ СЕССИИ (без изменений) ==================
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]

# ================== UI ИСТОРИЯ ЧАТА (без изменений, отладка только в новом сообщении) ==================
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Мы не будем отлаживать историю, только новый ответ, чтобы не загромождать экран
        if "chart" in message and message["chart"]:
            st.markdown("_(График из истории. Для отладки задайте новый вопрос.)_")

# ================== UI ПОЛЕ ВВОДА И ОБРАБОТКА ЗАПРОСА ==================
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

        # --- НАЧАЛО ГЛАВНОГО ОТЛАДОЧНОГО БЛОКА ---
        if chart_data:
            st.markdown("---")
            st.subheader("ОТЛАДОЧНАЯ ИНФОРМАЦИЯ")
            try:
                # Шаг 1: Показываем сырые данные, которые пришли от n8n
                st.markdown("**Шаг 1: Сырые данные `chart_data` от n8n**")
                st.json(chart_data)

                data_list = chart_data.get('data')
                if not data_list:
                    st.error("ОШИБКА: в `chart_data` отсутствует или пуст ключ 'data'.")
                else:
                    # Шаг 2: Создаем DataFrame и смотрим его структуру
                    st.markdown("**Шаг 2: DataFrame, созданный из данных (до очистки)**")
                    df = pd.DataFrame(data_list)
                    st.dataframe(df)
                    st.markdown("Типы данных в колонках (до очистки):")
                    st.text(df.dtypes)

                    # Шаг 3: Проверяем имена колонок
                    st.markdown("**Шаг 3: Проверка имен колонок**")
                    x_col = chart_data.get('x_column')
                    y_col = chart_data.get('y_column')
                    st.write(f"Имя колонки для X-оси: `{x_col}`")
                    st.write(f"Имя колонки для Y-оси: `{y_col}`")
                    
                    if not x_col or not y_col:
                        st.error("ОШИБКА: Имена колонок (x_column или y_column) не пришли от n8n.")
                    elif y_col not in df.columns:
                        st.error(f"ОШИБКА: Колонки `{y_col}` НЕТ в DataFrame.")
                    else:
                        # Шаг 4: Показываем колонку Y до и после каждого шага очистки
                        st.markdown(f"**Шаг 4: Пошаговая очистка колонки `{y_col}`**")
                        
                        st.markdown("4.1. Колонка КАК ЕСТЬ (до очистки):")
                        st.dataframe(df[[y_col]])

                        # Превращаем в строку для обработки
                        clean_series = df[y_col].astype(str)
                        st.markdown("4.2. После `.astype(str)`:")
                        st.dataframe(clean_series)

                        # Убираем пробелы
                        clean_series = clean_series.str.replace(' ', '', regex=False)
                        st.markdown("4.3. После `.str.replace(' ', '')`:")
                        st.dataframe(clean_series)

                        # Меняем запятые
                        clean_series = clean_series.str.replace(',', '.', regex=False)
                        st.markdown("4.4. После `.str.replace(',', '.')`:")
                        st.dataframe(clean_series)

                        # Шаг 5: Пробуем конвертировать в число и смотрим результат
                        st.markdown("**Шаг 5: Результат конвертации в число**")
                        final_series = pd.to_numeric(clean_series, errors='coerce')
                        st.dataframe(final_series)
                        st.markdown("Тип данных колонки Y после конвертации:")
                        st.text(final_series.dtypes)
                        
                        st.markdown("---")
                        st.info("Отладочная информация закончена. Если вы видите это, значит, код не упал с ошибкой. Посмотрите, есть ли в Шаге 5 числа или там 'NaN'.")


            except Exception as e:
                st.error(f"КОД УПАЛ С ОШИБКОЙ ВО ВРЕМЯ ОТЛАДКИ: {e}")
        # --- КОНЕЦ ГЛАВНОГО ОТЛАДОЧНОГО БЛОКА ---

    # Сохранение в историю (без изменений)
    st.session_state.messages.append({
        "role": "assistant", 
        "content": response_text, 
        "chart": chart_data
    })