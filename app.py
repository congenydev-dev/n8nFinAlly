import streamlit as st
import requests
import json
import pandas as pd
# Импортируем исполнение кода
from io import StringIO
import contextlib

# ... (ваш существующий код: N8N_WEBHOOK_URL, css_style, st.markdown, st.session_state) ...

# ... (ваш существующий цикл for message in st.session_state.messages) ...

if prompt := st.chat_input("Your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        payload = {"message": prompt}
        with st.spinner('Агент думает...'):
            response = requests.post(N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            
            # --- ИЗМЕНЕНИЕ 1: Ожидаем JSON с тремя ключами ---
            n8n_response_data = response.json()
            
            # Извлекаем компоненты
            response_text = n8n_response_data.get("text", "Извините, ответ не получен.")
            response_code = n8n_response_data.get("code", "")
            response_data_json = n8n_response_data.get("data", None)
            
            # --- Сохраняем текстовый ответ в историю ---
            st.session_state.messages.append({"role": "assistant", "content": response_text})
            with st.chat_message("assistant"):
                st.markdown(response_text)
            
            # --- ИЗМЕНЕНИЕ 2: Исполнение кода для визуализации ---
            if response_code:
                st.markdown("---") # Визуальный разделитель
                st.markdown("**Визуализация данных:**")
                
                # Если n8n прислал данные, создаем из них DataFrame, доступный для кода
                if response_data_json:
                    # Создаем глобальную переменную 'df'
                    df = pd.DataFrame(response_data_json)
                else:
                    df = None # Если данных нет, df будет None

                # Исполняем Python-код, присланный LLM/n8n
                with st.chat_message("assistant"):
                    try:
                        # Захватываем вывод print(), чтобы он не загромождал консоль
                        with contextlib.redirect_stdout(StringIO()):
                            # Используем exec для выполнения сгенерированного кода
                            exec(response_code, globals())
                    except Exception as e:
                        st.error(f"Не удалось построить график. Ошибка в коде: {e}")

    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка подключения к n8n workflow: {e}")
    except json.JSONDecodeError:
        st.error("Ошибка декодирования JSON: N8n вернул неверный формат.")