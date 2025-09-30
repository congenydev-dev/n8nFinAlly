import json
import uuid
import requests
import streamlit as st

# ========= Config =========
URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"  # Production URL
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 120

st.set_page_config(page_title="Аналитический AI-агент", layout="wide")
st.title("Аналитический AI-агент")
st.caption("Пишите вопрос — агент сам выберет источник (тексты/встречи) и ответит на русском.")

# ========= Helpers =========
TEXT_KEYS = ("text", "text_markdown", "text_response", "output", "message")

def _clean_json_text(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.lstrip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip("` \n\r\t")
    return s

def _text_from_response(resp: requests.Response) -> str:
    """Возвращает человекочитаемый текст из ответа (JSON или text/plain)."""
    ctype = (resp.headers.get("content-type") or "").lower()
    body = resp.text

    # 1) Нормальный JSON
    if "application/json" in ctype:
        try:
            data = resp.json()
            if isinstance(data, dict):
                for k in TEXT_KEYS:
                    v = data.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass

    # 2) Текст с JSON внутри (или двойная сериализация)
    try:
        first = json.loads(_clean_json_text(body))
        if isinstance(first, dict):
            for k in TEXT_KEYS:
                v = first.get(k)
                if isinstance(v, str) and v.strip():
                    return v
            return json.dumps(first, ensure_ascii=False)
        if isinstance(first, str):
            # возможно, JSON-строка внутри строки
            try:
                second = json.loads(_clean_json_text(first))
                if isinstance(second, dict):
                    for k in TEXT_KEYS:
                        v = second.get(k)
                        if isinstance(v, str) and v.strip():
                            return v
                    return json.dumps(second, ensure_ascii=False)
                if isinstance(second, str):
                    return second
            except Exception:
                return first
    except Exception:
        pass

    # 3) Обычный текст
    return body

def ask_agent(prompt: str, session_id: str) -> str:
    r = requests.post(
        URL,
        json={"prompt": prompt, "sessionId": session_id},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    r.raise_for_status()
    return _text_from_response(r)

# ========= State =========
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "history" not in st.session_state:
    st.session_state.history = [
        {"role": "assistant", "content": "Какие данные проанализируем сегодня?"}
    ]

# ========= Render history =========
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ========= Input & answer =========
if user_text := st.chat_input("Ваш вопрос…"):
    # мгновенно отрисуем пользователя
    with st.chat_message("user"):
        st.markdown(user_text)
    st.session_state.history.append({"role": "user", "content": user_text})

    # запрос к агенту
    with st.chat_message("assistant"):
        with st.spinner("Анализирую…"):
            try:
                text = ask_agent(user_text.strip(), st.session_state.session_id)
                st.markdown(text or "_пустой ответ_")
                st.session_state.history.append({"role": "assistant", "content": text or ""})
            except requests.exceptions.ReadTimeout:
                st.error("Таймаут ожидания ответа. Проверь узел Respond to Webhook или сократи запрос.")
            except requests.exceptions.RequestException as e:
                st.error(f"Ошибка подключения к workflow: {e}")
            except Exception as e:
                st.error(f"Неожиданная ошибка: {e}")
