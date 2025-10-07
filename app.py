import re
import json
import time
import uuid
import requests
import pandas as pd
import streamlit as st

# ========= КОНФИГ =========
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 240)           # connect=10s, read=240s (4 мин)
SESSION_TTL_SEC = 3600        # авто-ресет контекста через 1 час неактивности

st.set_page_config(page_title="Analitical Agent", layout="wide")

# ========= СЕССИЯ/РЕСЕТ =========
def reset_chat():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = [{"role": "assistant", "content": "Whom are we firing today?"}]
    st.session_state.session_started_at = time.time()
    st.session_state.last_interaction = time.time()

if "session_id" not in st.session_state:
    reset_chat()
if "session_started_at" not in st.session_state:
    st.session_state.session_started_at = time.time()
if "last_interaction" not in st.session_state:
    st.session_state.last_interaction = time.time()

# авто-ресет по TTL
now = time.time()
if now - st.session_state.last_interaction > SESSION_TTL_SEC:
    reset_chat()
    st.toast("Новый диалог: сессия была неактивна > 1 часа.", icon="🧹")

# ручной ресет
st.sidebar.button("🧹 Новый диалог", on_click=reset_chat)
st.sidebar.caption(f"Сессия: {st.session_state.session_id[:8]}…  • TTL: {SESSION_TTL_SEC//60} мин")

# ========= ПАРСЕР ОТВЕТА =========
def _try_parse_json_string(s: str):
    """Снять ```json ... ``` и распарсить. Возвращает dict/list или None."""
    if not isinstance(s, str):
        return None
    txt = s.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json|JSON)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    # если есть лишний префикс — вытащим первую {...}
    if not txt.lstrip().startswith("{"):
        m = re.search(r"\{[\s\S]*\}\s*$", txt)
        if m:
            txt = m.group(0)
    try:
        return json.loads(txt)
    except Exception:
        return None

def _dig_for_output(obj):
    """Рекурсивно находит первый dict с ключом 'output' (учитывает строки с JSON, массивы и обёртки)."""
    if isinstance(obj, str):
        parsed = _try_parse_json_string(obj)
        return _dig_for_output(parsed) if parsed is not None else None

    if isinstance(obj, dict):
        if "output" in obj and isinstance(obj["output"], str):
            parsed = _try_parse_json_string(obj["output"])
            if parsed is not None:
                return _dig_for_output(parsed)

        if "output" in obj and isinstance(obj["output"], dict):
            return obj["output"]

        for k in ("json", "data", "body", "result", "response"):
            if k in obj:
                got = _dig_for_output(obj[k])
                if got is not None:
                    return got

        for v in obj.values():
            got = _dig_for_output(v)
            if got is not None:
                return got
        return None

    if isinstance(obj, list):
        for el in obj:
            got = _dig_for_output(el)
            if got is not None:
                return got
    return None

def parse_n8n_response(response_json):
    """Ждём {'output': {'analytical_report': str, 'chart_data': null|{...}}} — с любыми обёртками/кодфенсами."""
    try:
        out = _dig_for_output(response_json)
        if not isinstance(out, dict):
            return {"text": "Не найден корректный 'output' в ответе сервера.", "chart": None}

        # разворачиваем лишние nesting-и: {"output":{"output":{...}}}
        while isinstance(out, dict) and "output" in out and isinstance(out["output"], dict):
            out = out["output"]

        text = out.get("analytical_report", "Отчёт отсутствует.")
        chart = out.get("chart_data", None)
        return {"text": text, "chart": chart}
    except Exception as e:
        return {"text": f"Критическая ошибка парсинга: {e}\nСырой ответ: {response_json}", "chart": None}

# ========= СЕТЕВОЙ ВЫЗОВ =========
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

# ========= УТИЛИТЫ ДЛЯ ГРАФИКОВ =========
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
    return str(s).replace("\u00A0", " ").strip().lower()

def show_chart(spec: dict):
    if not spec:
        return
    data = spec.get("data")
    x_key = spec.get("x_column")
    y_key = spec.get("y_column")            # одиночная серия
    y_keys = spec.get("y_columns")          # мульти-серия wide
    color_col = spec.get("color_column")    # мульти-серия long
    ctype = (spec.get("type") or "bar_chart").lower()
    width = spec.get("width", "stretch")
    height = spec.get("height", "content")

    if not (data and x_key and (y_key or y_keys)):
        st.error("chart_data неполный: нужны data, x_column и y_column|y_columns.")
        return

    # df
    df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)

    # нормализация чисел
    def _clean_num(s: pd.Series) -> pd.Series:
        return (s.astype(str)
                 .str.replace("\u00A0","",regex=False)
                 .str.replace("%","",regex=False)
                 .str.replace(" ","",regex=False)
                 .str.replace(",",".",regex=False)
                 .pipe(pd.to_numeric, errors="coerce"))

    # сортируем по X
    if x_key in df.columns:
        df = df.sort_values(x_key)

    if ctype == "line_chart":
        if y_keys:  # wide-format multi-series
            # только реально существующие и численные колонки
            cols = [y for y in y_keys if y in df.columns]
            if not cols:
                st.error("Нет ни одной из указанных y_columns в данных.")
                return
            for y in cols:
                df[y] = _clean_num(df[y])
            plot_df = df[[x_key] + cols].dropna(how="all", subset=cols)
            if plot_df.empty:
                st.info("График не построен: все значения метрик пусты после очистки.")
                return
            st.line_chart(plot_df, x=x_key, y=cols, width=width, height=height)
        else:
            # single-series (and possibly long-format if color_col is present)
            if color_col and color_col in df.columns:
                # long format: нужно развернуть в wide, чтобы отдать несколько линий
                # pivot: index=x, columns=color, values=y
                df[y_key] = _clean_num(df[y_key])  # так?
                pivot = df.pivot(index=x_key, columns=color_col, values=y_key).reset_index()
                # Streamlit line_chart поддерживает список y
                y_cols = [c for c in pivot.columns if c != x_key]
                st.line_chart(pivot, x=x_key, y=y_cols, width=width, height=height)
            else:
                # single line
                df[y_key] = _clean_num(df[y_key])
                plot_df = df[[x_key, y_key]].dropna(subset=[y_key])
                if plot_df.empty:
                    st.info("График не построен: значения метрики пусты после очистки.")
                    return
                st.line_chart(plot_df, x=x_key, y=y_key, width=width, height=height)
    else:
        # бар-чарт без deprecated use_container_width
        st.bar_chart(df, x=x_key, y=y_key or y_keys, width=width, height=height)

# ========= РЕНДЕР ИСТОРИИ =========
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart"):
            show_chart(msg["chart"])

# ========= ВВОД ПОЛЬЗОВАТЕЛЯ / ОТВЕТ =========
if prompt := st.chat_input("Ваш вопрос..."):
    st.session_state.last_interaction = time.time()

    # 1) показать сообщение пользователя и записать в историю
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2) запрос к n8n
    resp = ask_agent(prompt)
    text = resp.get("text", "_Пустой ответ от агента_")
    chart = resp.get("chart")

    # 3) добавить ответ ассистента в историю и пере-рендерить РОВНО один раз
    st.session_state.messages.append({"role": "assistant", "content": text, "chart": chart})
    st.rerun()
