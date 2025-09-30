import uuid
import requests
import streamlit as st

URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 120)

st.set_page_config(page_title="Аналитический AI-агент", layout="wide")
st.title("Аналитический AI-агент")
st.caption("Чат: агент выдаёт структурированный JSON, отображается только текст ответа.")

# ---------- helpers ----------
def _strip_fences(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()
    if s.startswith("```"):
        s = s.lstrip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip("` \n\r\t")
    return s

def _first_dict(x):
    """Вернёт первый словарь из x: dict -> dict, list -> первый dict, иначе None."""
    if isinstance(x, dict):
        return x
    if isinstance(x, list):
        for el in x:
            if isinstance(el, dict):
                return el
    return None

def ask_agent(q: str, sid: str) -> dict:
    r = requests.post(
        URL,
        json={"prompt": q, "sessionId": sid},
        headers={"x-session-id": sid},
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    # 1) пробуем JSON
    payload = None
    try:
        payload = r.json()
    except Exception:
        return {"ok": True, "text_response": r.text}

    # 2) если это массив — возьмём первый объект
    obj = _first_dict(payload) or {}
    # 3) если внутри есть output — распакуем
    if isinstance(obj.get("output"), dict):
        obj = obj["output"]

    text = (
        obj.get("text_response")
        or obj.get("text_markdown")
        or obj.get("text")
        or ""
    )
    return {
        "ok": bool(obj.get("ok", True)),
        "text_response": _strip_fences(text),
        "warnings": obj.get("warnings", []) or [],
        "errors": obj.get("errors", []) or [],
        "sources": obj.get("sources", []) or [],
    }

# ---------- state ----------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "chat" not in st.session_state:
    st.session_state.chat = [{"role": "assistant", "content": "Какие данные проанализируем сегодня?"}]

# ---------- history ----------
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ---------- input ----------
if q := st.chat_input("Ваш вопрос…"):
    st.session_state.chat.append({"role": "user", "content": q})
    with st.chat_message("assistant"):
        with st.spinner("Анализирую…"):
            try:
                p = ask_agent(q.strip(), st.session_state.session_id)
                text = p.get("text_response") or "_пустой ответ_"
                if p.get("errors"):
                    st.error("; ".join(map(str, p["errors"])))
                if p.get("warnings"):
                    st.info("; ".join(map(str, p["warnings"])))
            except requests.exceptions.ReadTimeout:
                text = "Таймаут ожидания ответа (проверь Respond to Webhook или сократи запрос)."
            except requests.exceptions.RequestException as e:
                text = f"Ошибка подключения к workflow: {e}"
            except Exception as e:
                text = f"Неожиданная ошибка: {e}"
        st.markdown(text)
    st.session_state.chat.append({"role": "assistant", "content": text})
