import streamlit as st
import requests

# URL вашего активного вебхука из n8n
N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"

# --- Секция для изменения стиля ---
# Просто меняйте коды цветов здесь, чтобы найти свой стиль
css_dark_theme = """
<style>
/* Основной фон */
[data-testid="stAppViewContainer"] > .main {
    background-color: #0E1117;
}

/* Фон заголовка */
[data-testid="stHeader"] {
    background-color: #1c212e;
}

/* Основной цвет текста */
.st-emotion-cache-183lzff {
    color: #FAFAFA;
}

/* Фон для сообщений в чате */
[data-testid="stChatMessage"] {
    background-color: #262730;
    border-radius: 10px; /* Скругленные углы */
    padding: 12px;
}
</style>
"""
st.markdown(css_dark_theme, unsafe_allow_html=True)
# --- Конец секции стиля ---


# --- Основная часть приложения ---
st.title("🤖Приветствую. Я ваш Аналитический Интеллектуальный Агент, готовый к обработке. И помните: если будете долго задавать вопрос, не волнуйтесь — я не заржавею, скорее, закодируюсь")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять?"}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        payload = {"message": prompt}
        with st.spinner('Thinking...'):
            response = requests.post(N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            bot_response = response.json().get("choices", [{}])[0].get("message", {}).get("content", "Sorry, something went wrong.")

        st.session_state.messages.append({"role": "assistant", "content": bot_response})
        with st.chat_message("assistant"):
            st.markdown(bot_response)
    except requests.exceptions.RequestException as e:

        st.error(f"Error connecting to n8n workflow: {e}")
