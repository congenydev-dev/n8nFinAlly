import streamlit as st
import requests

N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"

css_style = """
<style>
[data-testid="stAppViewContainer"] > .main {
    background-color: #1E1E1E;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    min-height: 100vh;
}
[data-testid="stHeader"] {
    background-color: rgba(0,0,0,0);
}
.st-emotion-cache-183lzff {
    color: #FAFAFA;
}
[data-testid="stChatMessage"] {
    background-color: #262730;
    border-radius: 10px;
    padding: 12px;
}
[data-testid="stChatInput"] {
    background-color: #1E1E1E;
}
[data-testid="stChatInput"] textarea {
    height: 120px;
    font-size: 1.1rem;
}
</style>
"""
st.markdown(css_style, unsafe_allow_html=True)

st.markdown("<div style='text-align: center;'>©Приветствую. Я ваш<br>Аналитический<br>Интеллектуальный Агент,<br>готовый к обработке. И помните:<br>если будете долго задавать<br>вопрос, не волнуйтесь — я не<br>заржавею, скорее, закодируюсь</div>", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "## Кого будем увольнять?"}]

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