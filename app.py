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
    st.toast("New dialog: session was inactive > 1 hour.")

# ручной ресет
st.sidebar.button(" New Chat", on_click=reset_chat)
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

# ========= РЕНДЕР ГРАФИКОВ =========
def show_chart(spec: dict):
    if not spec:
        return

    # --- извлечение параметров ---
    data      = spec.get("data")
    x_key     = spec.get("x_column")
    y_key     = spec.get("y_column")           # одиночная серия
    y_keys    = spec.get("y_columns")          # мульти-серия (wide)
    color_col = spec.get("color_column")       # длинная форма (long → wide)
    ctype     = (spec.get("type") or "bar_chart").lower()
    sort_flag = (spec.get("sort") or None)     # "y_asc" | "y_desc" | None

    # width/height: Streamlit ждёт int|None
    def _as_size(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return int(v)
        try:
            return int(str(v).strip())
        except Exception:
            return None

    width  = _as_size(spec.get("width"))
    height = _as_size(spec.get("height"))
    use_container_width = spec.get("use_container_width", True) if width is None else False

    if not (data and x_key and (y_key or y_keys or (y_key and color_col))):
        st.error("chart_data неполный: нужны data, x_column и (y_column | y_columns | y_column+color_column).")
        return

    # --- dataframe ---
    df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)

    # --- очистка чисел ---
    def _clean_num(s: pd.Series) -> pd.Series:
        return (
            s.astype(str)
             .str.replace("\u00A0","",regex=False)  # NBSP
             .str.replace("%","",regex=False)
             .str.replace(" ","",regex=False)
             .str.replace(",",".",regex=False)
             .pipe(pd.to_numeric, errors="coerce")
        )

    # --- сортировка (НЕ сортируем по X по умолчанию) ---
    def _maybe_sort(df: pd.DataFrame) -> pd.DataFrame:
        # удаляем дубли (особенно пары x,y)
        if y_key and y_key in df.columns:
            df = df.drop_duplicates(subset=[x_key, y_key], keep="first")
        else:
            df = df.drop_duplicates()

        if sort_flag in ("y_asc", "y_desc"):
            asc = (sort_flag == "y_asc")
            # single y
            if y_key and y_key in df.columns:
                tmp = df.copy()
                tmp[y_key] = _clean_num(tmp[y_key])
                return tmp.sort_values(y_key, ascending=asc)
            # wide y_columns
            if y_keys:
                cols = [c for c in y_keys if c in df.columns]
                if cols:
                    tmp = df.copy()
                    for c in cols:
                        tmp[c] = _clean_num(tmp[c])
                    tmp["_sum_y"] = tmp[cols].sum(axis=1, skipna=True)
                    tmp = tmp.sort_values("_sum_y", ascending=asc).drop(columns="_sum_y")
                    return tmp
            # long (y + color)
            if color_col and y_key and y_key in df.columns:
                tmp = df.copy()
                tmp[y_key] = _clean_num(tmp[y_key])
                agg = (tmp.groupby(x_key, as_index=False)[y_key]
                           .sum()
                           .sort_values(y_key, ascending=asc))
                order = agg[x_key].tolist()
                df[x_key] = pd.Categorical(df[x_key], categories=order, ordered=True)
                return df.sort_values(x_key)
        return df

    df = _maybe_sort(df)

    # --- построение ---
    if ctype == "line_chart":
        if y_keys:  # wide multi-series
            cols = [y for y in y_keys if y in df.columns]
            if not cols:
                st.error("Нет ни одной из указанных y_columns в data.")
                return
            for y in cols:
                df[y] = _clean_num(df[y])
            plot_df = df[[x_key] + cols].dropna(how="all", subset=cols)
            if plot_df.empty:
                st.info("Все значения метрик пусты после очистки.")
                return
            st.line_chart(
                plot_df, x=x_key, y=cols,
                width=width, height=height, use_container_width=use_container_width
            )

        elif color_col and color_col in df.columns and y_key in df.columns:
            df[y_key] = _clean_num(df[y_key])
            pivot = df.pivot(index=x_key, columns=color_col, values=y_key).reset_index()
            y_cols = [c for c in pivot.columns if c != x_key]
            st.line_chart(
                pivot, x=x_key, y=y_cols,
                width=width, height=height, use_container_width=use_container_width
            )

        else:
            if y_key not in df.columns:
                st.error("y_column не найден в data.")
                return
            df[y_key] = _clean_num(df[y_key])
            plot_df = df[[x_key, y_key]].dropna(subset=[y_key])
            if plot_df.empty:
                st.info("Значения метрики пустые после очистки.")
                return
            st.line_chart(
                plot_df, x=x_key, y=y_key,
                width=width, height=height, use_container_width=use_container_width
            )

    else:  # BAR
        if y_keys:  # wide multi-series
            cols = [y for y in y_keys if y in df.columns]
            if not cols:
                st.error("Нет ни одной из указанных y_columns в data.")
                return
            for y in cols:
                df[y] = _clean_num(df[y])
            plot_df = df[[x_key] + cols].dropna(how="all", subset=cols)
            if plot_df.empty:
                st.info("Все значения метрик пусты после очистки.")
                return
            st.bar_chart(
                plot_df, x=x_key, y=cols,
                width=width, height=height, use_container_width=use_container_width
            )

        elif color_col and color_col in df.columns and y_key in df.columns:
            df[y_key] = _clean_num(df[y_key])
            pivot = df.pivot(index=x_key, columns=color_col, values=y_key).reset_index()
            y_cols = [c for c in pivot.columns if c != x_key]
            st.bar_chart(
                pivot, x=x_key, y=y_cols,
                width=width, height=height, use_container_width=use_container_width
            )

        else:
            if y_key not in df.columns:
                st.error("y_column не найден в data.")
                return
            df[y_key] = _clean_num(df[y_key])
            plot_df = df[[x_key, y_key]].dropna(subset=[y_key])
            if plot_df.empty:
                st.info("Значения метрики пустые после очистки.")
                return
            st.bar_chart(
                plot_df, x=x_key, y=y_key,
                width=width, height=height, use_container_width=use_container_width
            )

# ========= РЕНДЕР ИСТОРИИ =========
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart"):
            show_chart(msg["chart"])

# ========= ВВОД ПОЛЬЗОВАТЕЛЯ / ОТВЕТ =========
if prompt := st.chat_input("Go slow—I’m cloud-based. Rust requires metal."):
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
