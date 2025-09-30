import time
import uuid
import random
import requests
import streamlit as st

# ================== CONFIG ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 120)  # connect, read
MAX_RETRIES = 3      # мягкие ретраи на 429

st.set_page_config(page_title="Аналитический AI-агент", layout="wide")
st.title("Аналитический AI-агент")

# --------- Sidebar (debug / settings) ----------
with st.sidebar:
    st.caption("⚙️ Настройки")
    url = st.text_input("Webhook URL", value=N8N_URL)
    debug = st.checkbox("Показывать сырой ответ", value=False)
    st.caption("Команды: `/clear` — очистить чат, `/newsid` — новый SessionId`")

# --------------- Helpers ----------------
def _strip_fences(s: str) -> str:
    if not isinstance(s, str): return ""
    s = s.strip()
    if s.startswith("```"):
        s = s.lstrip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip("` \n\r\t")
    return s

def _first_dict(x):
    if isinstance(x, dict):
        return x
    if isinstance(x, list):
        for el in x:
            if isinstance(el, dict):
                return el
    return {}

def _extract_payload(obj: dict) -> dict:
    """Приводим к контракту: {ok, text_response, warnings, errors, sources}."""
    if isinstance(obj.get("output"), dict):
        obj = obj["output"]

    text = obj.get("text_response") or obj.get("text_markdown") or obj.get("text") or ""
    return {
        "ok": bool(obj.get("ok", True)),
        "text_response": _strip_fences(text),
        "warnings": obj.get("warnings", []) or [],
        "errors": obj.get("errors", []) or [],
        "sources": obj.get("sources", []) or [],
    }

def ask_agent(prompt: str, session_id: str) -> dict:
    """POST с мягкими ретраями на 429; всегда возвращает словарь."""
    attempt = 0
    while True:
        attempt += 1
        r = requests.post(
            url,
            json={"prompt": prompt, "sessionId": session_id},
            headers={"x-session-id": session_id},
            timeout=TIMEOUT,
        )
        # ретраи только на 429
        if r.status_code == 429 and attempt <= MAX_RETRIES:
            backoff = min(60, (2 ** (attempt - 1)) * 3 + random.randint(0, 2))
            time.sleep(backoff)
            continue
        r.raise_for_status()

        # нормальный JSON
        try:
            raw = r.json()
        except Exception:
            return {"ok": True, "text_response": r.text, "warnings": [], "errors": []}

        obj = _first_dict(raw)
        payload = _extract_payload(obj)
        if debug:
            st.sidebar.json(raw)
        return payload

# ----------------- State -----------------
if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())
if "chat" not in st.session_state:
    st.session_state.chat = [{"role": "assistant", "content": "Какие данные проанализируем сегодня?"}]

# ----------------- History ----------------
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ----------------- Input ------------------
q = st.chat_input("Ваш вопрос…")
if q:
    # команды
    if q.strip().lower() == "/clear":
        st.session_state.chat = [{"role": "assistant", "content": "Чат очищен. Чем помочь?"}]
        st.rerun()
    if q.strip().lower() == "/newsid":
        st.session_state.sid = str(uuid.uuid4())
        st.session_state.chat.append({"role": "assistant", "content": f"Создан новый SessionId: `{st.session_state.sid}`"})
        st.rerun()

    st.session_state.chat.append({"role": "user", "content": q})
    with st.chat_message("assistant"):
        with st.spinner("Анализирую…"):
            try:
                p = ask_agent(q.strip(), st.session_state.sid)
                text = p.get("text_response") or "_пустой ответ_"
            except requests.exceptions.ReadTimeout:
                text = "Таймаут ожидания ответа."
            except requests.exceptions.RequestException as e:
                text = f"Ошибка подключения: {e}"
            except Exception as e:
                text = f"Неожиданная ошибка: {e}"
        st.markdown(text)
    st.session_state.chat.append({"role": "assistant", "content": text})
