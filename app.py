import streamlit as st
import requests
import uuid
import time
import random

# ================== КОНФИГУРАЦИЯ ==================
# URL вашего вебхука в n8n
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 120)  # (connect, read) в секундах

# ================== НАСТРОЙКА СТРАНИЦЫ ==================
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")


# ================== ПАРСИНГ ОТВЕТА N8N ==================
def parse_n8n_response(response_json: list | dict) -> dict:
    """Извлекает полезные данные из JSON-ответа от n8n."""
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
    """Отправляет POST-запрос к n8n и возвращает обработанный ответ."""
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
    st.text_area(
        "Системные инструкции", 
        "Ты — полезный аналитический AI-агент...", 
        height=100, 
        disabled=True
    )
    st.slider("Температура", 0.0, 1.0, 0.7, disabled=True)

    with st.expander("Дополнительные настройки"):
        url_input = st.text_input("Webhook URL", value=N8N_URL)
        debug_mode = st.checkbox("Показывать сырой ответ JSON", value=False)
        st.caption("Команды в чате: `/clear` для очистки, `/newsid` для новой сессии.")


# ================== ИНИЦИАЛИЗАЦИЯ СЕССИИ ЧАТА ==================
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Какие данные проанализируем сегодня?"}]


# ================== UI: ОТОБРАЖЕНИЕ ИСТОРИИ ЧАТА ==================
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# ================== UI: ПОЛЕ ВВОДА И ОБРАБОТКА ЗАПРОСА ==================
if prompt := st.chat_input("Ваш вопрос..."):
    # Обработка команд
    if prompt.strip().lower() == "/clear":
        st.session_state.messages = [{"role": "assistant", "content": "Чат очищен. Чем могу помочь?"}]
        st.rerun()
    
    if prompt.strip().lower() == "/newsid":
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages.append({"role": "assistant", "content": f"Создана новая сессия: `{st.session_state.session_id}`"})
        st.rerun()

    # Добавляем и отображаем сообщение пользователя
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Отображение ответа ассистента (ИЗМЕНЕННАЯ И ИСПРАВЛЕННАЯ ЧАСТЬ)
    with st.chat_message("assistant"):
        # Создаем пустой контейнер-плейсхолдер
        message_placeholder = st.empty()
        # Показываем спиннер в плейсхолдере
        message_placeholder.markdown("Анализирую данные...")
        
        # Получаем ответ от агента
        response_data = ask_agent(prompt, st.session_state.session_id, url_input, debug_mode)
        response_text = response_data.get("text") or "_Пустой ответ от агента_"
        
        # Заменяем спиннер на финальный текст в том же плейсхолдере
        message_placeholder.markdown(response_text)

    # Сохранение финального ответа ассистента в историю
    st.session_state.messages.append({"role": "assistant", "content": response_text})