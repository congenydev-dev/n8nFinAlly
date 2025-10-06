import streamlit as st
import requests
import uuid
import pandas as pd
import json  # <-- добавили

# ========= КОНФИГ =========
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 240)  # connect=10s, read=240s (4 минуты)

st.set_page_config(page_title="Analitical Agent", layout="wide")

# ========= СЕССИЯ =========
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Whom are we firing today?"}]

# ========= УТИЛИТЫ =========
def _dig_for_output(obj):
    """Рекурсивно находит первый dict с ключом 'output' в любых обёртках/массивах/строках."""
    if isinstance(obj, dict):
        if "output" in obj and isinstance(obj["output"], dict):
            return obj["output"]
        # популярные обёртки n8n
        for k in ("json", "data", "body", "result"):
            if k in obj:
                got = _dig_for_output(obj[k])
                if got is not None:
                    return got
        # пройтись по всем значениям (на всякий)
        for v in obj.values():
            got = _dig_for_output(v)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for el in obj:
            got = _dig_for_output(el)
            if got is not None:
                return got
    elif isinstance(obj, str):
        # иногда прилетает JSON-строка (в т.ч. в ```json ... ```)
        s = obj.strip()
        if s.startswith("```"):
            s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
        try:
            return _dig_for_output(json.loads(s))
        except Exception:
            pass
    return None

def parse_n8n_response(response_json):
    """Ожидаем {'output': {'analytical_report': str, 'chart_data': null|{...}}}"""
    try:
        out = _dig_for_output(response_json)
        if not isinstance(out, dict):
            return {"text": "Не найден ключ 'output' в ответе сервера.", "chart": None}
        text = out.get("analytical_report", "Отчёт отсутствует.")
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

def _norm_key(s: str) -> str:
    # унифицируем ключи: убираем NBSP, лишние пробелы, lower
    return str(s).replace("\u00A0", " ").strip().lower()

def show_chart(spec: dict):
    """Рендер bar/line на основе chart_data (нативные Streamlit-чарты)."""
    if not spec:
        return
    data = spec.get("data")
    x_key = spec.get("x_column")
    y_key = spec.get("y_column")
    ctype = (spec.get("type") or "bar_chart").lower()

    if not (data and x_key and y_key):
        st.error("chart_data неполный (нужны data/x_column/y_column).")
        return

    df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)

    # сопоставляем реальные колонки по нормализованным именам (на случай NBSP/регистра)
    cmap = {_norm_key(c): c for c in df.columns}
    x_col = cmap.get(_norm_key(x_key))
    y_col = cmap.get(_norm_key(y_key))
    if not x_col or not y_col:
        st.error(f"Колонки не найдены. Ожидались '{x_key}' и '{y_key}'.")
        st.write("columns:", list(df.columns))
        return

    df = df[[x_col, y_col]].rename(columns={x_col: x_key, y_col: y_key})

    # привести Y к числу
    df[y_key] = _to_numeric_series(df[y_key])
    df = df.dropna(subset=[y_key])
    if df.empty:
        st.info("График не построен: после очистки чисел данные пустые.")
        return

    # опциональная сортировка по Y, если когда-нибудь пришлёшь флаг
    sort_by_y = spec.get("sort_by_y")  # "asc" | "desc" | None
    if sort_by_y == "asc":
        df = df.sort_values(y_key, ascending=True)
    elif sort_by_y == "desc":
        df = df.sort_values(y_key, ascending=False)

    if ctype == "line_chart":
        st.line_chart(df, x=x_key, y=y_key, width="stretch", height="content")
    else:
        st.bar_chart(
            df,
            x=x_key,
            y=y_key,
            horizontal=bool(spec.get("horizontal", False)),
            sort=spec.get("sort", True),          # True | False | "col" | "-col"
            stack=spec.get("stack", None),         # True | False | "normalize" | "center" | "layered" | None
            use_container_width=True,
            height=420,
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
        else:
            st.info("График не отрисован: агент не вернул chart_data для этого ответа.")

    st.session_state.messages.append({"role": "assistant", "content": text, "chart": chart})
