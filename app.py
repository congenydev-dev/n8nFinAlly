import json, uuid, requests, pandas as pd
import streamlit as st

URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 120

st.set_page_config(page_title="Аналитический AI-агент", layout="wide")
st.title("Аналитический AI-агент")
st.caption("Пишите вопрос — агент сам выберет источник (тексты/встречи) и ответит на русском.")

# ---- helpers ----
def clean_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.lstrip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip("` \n\r\t")
    return t

def try_json(resp: requests.Response):
    ctype = resp.headers.get("content-type","").lower()
    txt = resp.text
    if "application/json" in ctype:
        try:
            return resp.json()
        except Exception:
            pass
    # иногда присылают текст с JSON-внутри
    try:
        return json.loads(clean_json(txt))
    except Exception:
        return None

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
    x = chart.get("x_column"); y = chart.get("y_column")
    if df.empty or not x or not y or x not in df.columns:
        return

    if isinstance(y, list):
        for i, col in enumerate(y):
            if col not in df.columns: 
                continue
            st.subheader(chart.get("title", f"{col} by {x}"))
            st.bar_chart(df[[x, col]].set_index(x), use_container_width=True, key=f"{key_prefix}-bar-{i}") \
                if chart.get("type") == "bar_chart" else \
                st.line_chart(df[[x, col]].set_index(x), use_container_width=True, key=f"{key_prefix}-line-{i}")
    else:
        if y not in df.columns: 
            return
        st.subheader(chart.get("title", f"{y} by {x}"))
        st.bar_chart(df[[x, y]].set_index(x), use_container_width=True, key=f"{key_prefix}-bar") \
            if chart.get("type") == "bar_chart" else \
            st.line_chart(df[[x, y]].set_index(x), use_container_width=True, key=f"{key_prefix}-line")

def post_to_n8n(prompt: str, session_id: str):
    r = requests.post(URL, json={"prompt": prompt, "sessionId": session_id},
                      timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    r.raise_for_status()
    return r

# ---- state ----
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "history" not in st.session_state:
    st.session_state.history = [{"role":"assistant","content":"Какие данные проанализируем сегодня?"}]

# ---- render history ----
for i, msg in enumerate(st.session_state.history):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        for ch_i, ch in enumerate(msg.get("charts", [])):
            draw_chart(ch, key_prefix=f"msg{i}-{ch_i}")

# ---- input ----
if user_text := st.chat_input("Ваш вопрос…"):
    st.session_state.history.append({"role":"user","content":user_text})
    with st.chat_message("assistant"):
        with st.spinner("Анализирую…"):
            try:
                resp = post_to_n8n(user_text.strip(), st.session_state.session_id)
                payload = try_json(resp)

                charts = []
                if isinstance(payload, dict):
                    text = payload.get("text_markdown") or payload.get("text_response") or ""
                    # поддержка одного графика или массива
                    if isinstance(payload.get("chart_data"), dict):
                        charts = [payload["chart_data"]]
                    elif isinstance(payload.get("charts"), list):
                        charts = payload["charts"]
                else:
                    text = resp.text  # пришёл чистый текст

                st.markdown(text or resp.text or "_пустой ответ_")
                for i, ch in enumerate(charts):
                    draw_chart(ch, key_prefix=f"last-{i}")

                st.session_state.history.append({"role":"assistant","content": text or resp.text, "charts": charts})

            except requests.exceptions.ReadTimeout:
                st.error("Таймаут ожидания ответа. Проверь настройки Respond to Webhook или сократи запрос.")
            except requests.exceptions.RequestException as e:
                st.error(f"Ошибка подключения к workflow: {e}")
            except Exception as e:
                st.error(f"Неожиданная ошибка: {e}")
