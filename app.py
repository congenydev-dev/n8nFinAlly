import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import numpy as np
import uuid

# ---------- Page & Layout ----------
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")
# ~20% ширины сайдбара
st.markdown("""
<style>
[data-testid="stSidebar"] { min-width: 20% !important; max-width: 20% !important; }
</style>
""", unsafe_allow_html=True)

# ---------- Config ----------
N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/550ca24c-1f7c-47fd-8f44-8028fb7ecd0d"

# ---------- Helpers ----------
def _to_df(data) -> pd.DataFrame:
    if isinstance(data, list):
        return pd.DataFrame(data)
    elif isinstance(data, dict):
        return pd.DataFrame([data])
    return pd.DataFrame()

def _soft_cast(df: pd.DataFrame, cols):
    if not cols:
        return df
    cols = [cols] if isinstance(cols, str) else list(cols)
    for c in cols:
        if c in df.columns:
            try:
                df[c] = pd.to_datetime(df[c]); continue
            except Exception:
                pass
            df[c] = pd.to_numeric(df[c], errors="ignore")
    return df

def _require_fields(d: dict, fields: list) -> bool:
    for f in fields:
        if d.get(f) in (None, "", []):
            st.warning(f"Ответ сервера не содержит обязательное поле '{f}'.")
            return False
    return True

@st.cache_data(ttl=600, show_spinner=False)
def fetch_from_n8n(prompt: str, session_id: str):
    payload = {"prompt": prompt, "sessionId": session_id}
    r = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def display_chart(chart_info: dict):
    """
    Поддерживаемые типы:
      bar_chart, line_chart, scatter, area, histogram, pie, box, heatmap
    Поля:
      data, type, x_column, y_column (str | list[str])
      title? z_column?/agg? (для heatmap), show_table?
    """
    try:
        df = _to_df(chart_info.get("data"))
        x_col = chart_info.get("x_column")
        y_col = chart_info.get("y_column")
        z_col = chart_info.get("z_column")
        chart_type = chart_info.get("type") or st.session_state.get("default_chart_type", "line_chart")
        chart_info["type"] = chart_type
        if "show_table" not in chart_info:
            chart_info["show_table"] = st.session_state.get("default_show_table", True)

        if not _require_fields(chart_info, ["x_column", "y_column"]):
            return

        # Сглаживание
        df = _soft_cast(df, [x_col, y_col] if not isinstance(y_col, list) else [x_col] + y_col)
        rw = st.session_state.get("rolling_window", 0)
        if rw and isinstance(y_col, str) and y_col in df.columns:
            df[y_col] = pd.Series(df[y_col]).rolling(rw).mean(); df = df.dropna()
        elif rw and isinstance(y_col, list):
            for _y in y_col:
                if _y in df.columns:
                    df[_y] = pd.Series(df[_y]).rolling(rw).mean()
            df = df.dropna(how="any")

        title = chart_info.get("title") or (f"{y_col} по {x_col}" if y_col and x_col else "Chart")

        # Построение
        if chart_type == "bar_chart":
            fig = px.bar(df, x=x_col, y=y_col, title=title, template="plotly_white", barmode="group")
        elif chart_type == "line_chart":
            fig = px.line(df, x=x_col, y=y_col, title=title, template="plotly_white", markers=True)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x_col, y=y_col, title=title, template="plotly_white")
        elif chart_type == "area":
            fig = px.area(df, x=x_col, y=y_col, title=title, template="plotly_white")
        elif chart_type == "histogram":
            y_one = y_col if isinstance(y_col, str) else None
            fig = px.histogram(df, x=x_col, y=y_one, title=title, template="plotly_white", nbins=30)
        elif chart_type == "pie":
            fig = px.pie(df, names=x_col, values=y_col if isinstance(y_col, str) else None,
                         title=title, hole=0.0)
        elif chart_type == "box":
            fig = px.box(df, x=x_col, y=y_col, title=title, template="plotly_white", points="outliers")
        elif chart_type == "heatmap":
            agg = (chart_info.get("agg") or "count").lower()
            if z_col and z_col in df.columns:
                if agg in ("sum", "mean", "median", "min", "max"):
                    pv = df.pivot_table(index=y_col, columns=x_col, values=z_col, aggfunc=agg)
                else:
                    pv = df.pivot_table(index=y_col, columns=x_col, values=z_col, aggfunc="count")
            else:
                pv = df.pivot_table(index=y_col, columns=x_col, aggfunc="size")
            pv = pv.sort_index(axis=0).sort_index(axis=1)
            fig = px.imshow(pv, title=title, aspect="auto")
        else:
            st.warning(f"Неизвестный тип графика: '{chart_type}'"); return

        st.plotly_chart(fig, use_container_width=True)
        if chart_info.get("show_table"):
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.error(f"Не удалось отобразить график. Ошибка: {e}")

# ---------- State ----------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Какие данные проанализируем сегодня?"}]
st.session_state.setdefault("agent_mode", "analytics")
st.session_state.setdefault("response_mode", "chat_and_charts")  # chat_only|charts_only|chat_and_charts
st.session_state.setdefault("default_chart_type", "line_chart")
st.session_state.setdefault("default_show_table", True)
st.session_state.setdefault("rolling_window", 0)
st.session_state.setdefault("show_raw_json", False)

# ---------- Sidebar (~20%) ----------
with st.sidebar:
    st.header("⚙️ Панель управления")

    st.subheader("Session")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🆕 Новый чат"):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = [{"role": "assistant", "content": "Новый сеанс. Что анализируем?"}]
            st.experimental_rerun()
    with c2:
        if st.button("🧹 Очистить историю"):
            st.session_state.messages = [{"role": "assistant", "content": "История очищена. Чем помочь?"}]
            st.experimental_rerun()
    if st.button("♻️ Очистить кэш"):
        try: fetch_from_n8n.clear()
        except Exception: pass
        st.success("Кэш очищен")

    st.divider()
    st.subheader("Data & RAG")
    st.text_input("Webhook (readonly)", value=N8N_WEBHOOK_URL, disabled=True)
    st.session_state.agent_mode = st.radio("Режим агента", ["analytics", "chat"],
                                           format_func=lambda v: "Аналитика" if v=="analytics" else "Чат")
    sys_prompt = st.text_area("Системная подсказка (опц.)", height=80, placeholder="Краткие правила для агента...")

    st.divider()
    st.subheader("Chart defaults")
    st.session_state.response_mode = st.radio(
        "Режим вывода",
        ["chat_only", "charts_only", "chat_and_charts"], index=2,
        format_func=lambda v: {"chat_only":"Только чат","charts_only":"Только графики","chat_and_charts":"Чат + графики"}[v]
    )
    st.session_state.default_chart_type = st.selectbox(
        "Тип по умолчанию",
        ["line_chart","bar_chart","scatter","area","histogram","pie","box","heatmap"], index=0
    )
    st.session_state.default_show_table = st.checkbox("Показывать таблицу", value=st.session_state.default_show_table)
    st.session_state.rolling_window = st.slider("Скользящее окно (0=выкл)", 0, 30, st.session_state.rolling_window)

    st.divider()
    st.subheader("Prompts (без автозапроса)")
    if st.button("📈 Продажи по месяцам (линии)"):
        st.session_state.draft_prompt = "Построй линию продаж по месяцам. x=month, y=sales"
    if st.button("📊 Топ категорий (бар)"):
        st.session_state.draft_prompt = "Построй bar_chart по категориям. x=category, y=revenue"
    if st.button("🔥 Плотность событий (heatmap)"):
        st.session_state.draft_prompt = "Сделай heatmap по weekday vs hour на моих событиях"

    st.divider()
    st.subheader("Dev")
    st.session_state.show_raw_json = st.checkbox("Показывать сырой JSON", value=st.session_state.show_raw_json)

# ---------- Header ----------
st.title("Аналитический AI-агент")
st.markdown("Здравствуйте! Я ваш аналитический AI-агент. Попросите меня визуализировать данные.")
st.divider()

# ---------- Draft prompt box ----------
if "draft_prompt" in st.session_state and st.session_state.draft_prompt:
    with st.container(border=True):
        st.caption("Черновик запроса (из быстрого примера)")
        with st.form("draft_form", clear_on_submit=True):
            draft = st.text_area("Отредактируйте и отправьте", value=st.session_state.draft_prompt, height=100)
            send = st.form_submit_button("➡️ Отправить")
        if send and draft.strip():
            st.session_state.messages.append({"role": "user", "content": draft.strip()})
            st.session_state.pop("draft_prompt", None)
            st.experimental_rerun()

# ---------- History ----------
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if st.session_state.response_mode in ["chat_only", "chat_and_charts"]:
            st.markdown(message["content"])
        if "chart" in message and st.session_state.response_mode in ["charts_only", "chat_and_charts"]:
            display_chart(message["chart"])

# ---------- Input ----------
if prompt := st.chat_input("Спросите что-нибудь о ваших данных..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        with st.spinner('Анализирую...'):
            meta = {
                "mode": st.session_state.agent_mode,
                "chart_default": st.session_state.default_chart_type,
                "show_table": st.session_state.default_show_table,
                "rolling": st.session_state.rolling_window,
                "system_prompt": (sys_prompt.strip() if sys_prompt else None),
                "response_mode": st.session_state.response_mode,
            }
            composed = f"{prompt}\n\n[META]{meta}"
            json_response = fetch_from_n8n(composed.strip(), st.session_state.session_id)

        if st.session_state.show_raw_json:
            with st.expander("RAW JSON от n8n"):
                st.json(json_response)

        text_response = json_response.get("text_response", "Получен пустой ответ от сервера.")
        chart_info = json_response.get("chart_data")

        assistant_message = {"role": "assistant", "content": text_response}
        if isinstance(chart_info, dict) and chart_info.get("data"):
            assistant_message["chart"] = chart_info

        st.session_state.messages.append(assistant_message)

        with st.chat_message("assistant"):
            if st.session_state.response_mode in ["chat_only", "chat_and_charts"]:
                st.markdown(text_response)
            if "chart" in assistant_message and st.session_state.response_mode in ["charts_only", "chat_and_charts"]:
                display_chart(assistant_message["chart"])

    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка подключения к workflow: {e}")
    except requests.exceptions.JSONDecodeError:
        st.error("Ответ сервера не JSON.")
    except Exception as e:
        st.error(f"Произошла ошибка: {e}")
