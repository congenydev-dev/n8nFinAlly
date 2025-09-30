import json
import uuid
import requests
import pandas as pd
import streamlit as st

# ---------------- Config ----------------
URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 120

st.set_page_config(page_title="Аналитический AI-агент", layout="wide")
st.title("Аналитический AI-агент")
st.caption("Пишите вопрос — агент сам выберет источник (тексты/встречи) и ответит на русском.")

# ---------------- Helpers ----------------
def clean_json_text(text: str) -> str:
    """Снимает обёртки ```json … ``` и лишние пробелы/бектики."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.lstrip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip("` \n\r\t")
    return t

def parse_payload_from_response(resp: requests.Response) -> dict | str:
    """
    Возвращает:
      - dict (если пришёл объект или текст с JSON внутри)
      - str (если это чистый текст)
    """
    ctype = (resp.headers.get("content-type") or "").lower()
    text = resp.text
    # если сервер честно прислал application/json
    if "application/json" in ctype:
        try:
            return resp.json()
        except Exception:
            pass
    # иногда присылают text/plain с JSON внутри
    try:
        first = json.loads(clean_json_text(text))
        if isinstance(first, str):
            # двойная сериализация: JSON-строка внутри строки
            try:
                return json.loads(clean_json_text(first))
            except Exception:
                return {"text_markdown": first}
        return first
    except Exception:
        return text  # обычный текст

def as_df(data):
    if isinstance(data, list):
        return pd.DataFrame(data)
    if isinstance(data, dict):
        return pd.DataFrame([data])
    return pd.DataFrame()

def draw_chart(chart: dict, key_prefix: str = ""):
    """
    chart = {
      "type": "bar_chart" | "line_chart",
      "x_column": "X",
      "y_column": "Y" | ["Y1","Y2"],
      "data": [ {X:..., Y:...}, ... ],
      "title": "..."
    }
    """
    if not isinstance(chart, dict):
        return
    df = as_df(chart.get("data", []))
    x = chart.get("x_column")
    y = chart.get("y_column")
    if df.empty or not x or not y or x not in df.columns:
        return

    title = chart.get("title", "")
    if isinstance(y, list):
        for i, col in enumerate(y):
            if col not in df.columns:
                continue
            if title:
                st.subheader(f"{title} — {col}")
            d = df[[x, col]].set_index(x)
            if chart.get("type") == "line_chart":
                st.line_chart(d, use_container_width=True, key=f"{key_prefix}-line-{i}")
            else:
                st.bar_chart(d, use_container_width=True, key=f"{key_prefix}-bar-{i}")
    else:
        if y not in df.columns:
            return
        if title:
            st.subheader(title)
        d = df[[x, y]].set_index(x)
        if chart.get("type") == "line_chart":
            st.line_chart(d, use_container_width=True, key=f"{key_prefix}-line")
        else:
            st.bar_chart(d, use_container_width=True, key=f"{key_prefix}-bar")

def post_to_n8n(prompt: str, session_id: str) -> requests.Response:
    r = requests.post(
        URL,
        json={"prompt": prompt, "sessionId": session_id},
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    r.raise_for_status()
    return r

# ---------------- State ----------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "history" not in st.session_state:
    st.session_state.his_
