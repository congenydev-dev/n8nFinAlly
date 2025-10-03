import streamlit as st
import requests
import uuid
import pandas as pd

# ========= КОНФИГ =========
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 240)  # connect=10s, read=240s (4 минуты)

st.set_page_config(page_title="Аналитический AI-агент", layout="wide")

# ========= СЕССИЯ =========
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]

# ========= УТИЛИТЫ =========
def parse_n8n_response(response_json):
    """Ожидаем {'output': {'analytical_report': str, 'chart_data': null|{...}}}"""
    try:
        data = response_json[0] if isinstance(response_json, list) and response_json else response_json
        out = data.get("output", {}) if isinstance(data, dict) else {}
        text = out.get("analytical_report", "Ошибка: не удалось извлечь текстовый отчёт из ответа.")
        chart = out.get("chart_data", None)
        return {"text": text, "chart": chart}
    except Exception as e:
        return {"text": f"Критическая ошибка парсинга: {e}\nСырой ответ: {response_json}", "chart": None}

def ask_agent(prompt: str) -> dict:
    headers = {"x-session-id": st.session_state.session_id}
    payload = {"prompt": prompt, "sessionId": st.session_state.session_id}
    try:
        r = requests.post(N8N_URL, json=payload, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return parse_n8n_response(r.json())
    except requests.exceptions.RequestException as e:
        return {"text": f"Ошибка подключения/таймаута: {e}", "chart": None}
    except Exception as e:
        return {"text": f"Неожиданная ошибка: {e}", "chart": None}

def _to_numeric_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.replace("\u00A0", "", regex=False)  # NBSP
         .str.replace("%", "", regex=False)
         .str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False)
         .pipe(pd.to_numeric, errors="coerce")
    )

def show_chart(spec: dict):
    """Только bar_chart и line_chart (нативный Streamlit)."""
    if not spec:
        return
    data = spec.get("data")
    x_col = spec.get("x_column")
    y_col = spec.get("y_column")
    chart_type = (spec.get("type") or "bar_chart").lower()

    if not (data and x_col and y_col):
        st.error("chart_data неполный (нужны data/x_column/y_column).")
        return

    df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)
    if x_col not in df.columns or y_col not in df.columns:
        st.error("Указанные колонки для графика не найдены в данных.")
        return

    df[y_col] = _to_numeric_series(df[y_col])
    df = df.dropna(subset=[y_col])
    if df.empty:
        st.warning("Данные для графика пустые после очистки.")
        return

    common = dict(x=x_col, y=y_col, use_container_width=True, height=420, sort=False)
    if chart_type == "line_chart":
        st.line_chart(df[[x_col, y_col]], **common)
    else:
        st.bar_chart(
            df[[x_col, y_col]],
            **common,
            horizontal=bool(spec.get("horizontal", False)),
            stack=spec.get("stack", None),
        )

# ========= РЕНДЕР ИСТОРИИ =========
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart"):
            show_chart(msg["chart"])

# ========= ВВОД ПОЛЬЗОВАТЕЛЯ =========
if prompt := st.chat_input("Ваш вопрос..."):
    # 1) Пишем пользователя в историю и рисуем его сообщение
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2) Синхронно спрашиваем n8n (до 4 минут, без спиннеров)
    resp = ask_agent(prompt)
    text = resp.get("text", "_Пустой ответ от агента_")
    chart = resp.get("chart")

    # 3) Рисуем ответ и добавляем его в историю
    with st.chat_message("assistant"):
        st.markdown(text)
        if chart:
            show_chart(chart)
    st.session_state.messages.append({"role": "assistant", "content": text, "chart": chart})
