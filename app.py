import streamlit as st
import requests
import uuid
import pandas as pd
import plotly.express as px

# ================== КОНФИГ ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 25)  # (connect, read) — короче, чтобы UI не "замирал"

# ================== СТРАНИЦА ==================
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")

# ================== СЕССИЯ ==================
ss = st.session_state
if "session_id" not in ss:
    ss.session_id = str(uuid.uuid4())
if "messages" not in ss:
    ss.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]
if "debug_mode" not in ss:
    ss.debug_mode = False
if "pending" not in ss:
    ss.pending = False
if "pending_prompt" not in ss:
    ss.pending_prompt = ""
if "fetch_in_progress" not in ss:
    ss.fetch_in_progress = False

# ================== УТИЛИТЫ ==================
def parse_n8n_response(response_json):
    """Ждём контракт: {'output': {'analytical_report': str, 'chart_data': null|{...}}}"""
    try:
        data = response_json[0] if isinstance(response_json, list) and response_json else response_json
        out = data.get("output", {}) if isinstance(data, dict) else {}
        text = out.get("analytical_report", "Ошибка: не удалось извлечь текстовый отчёт из ответа.")
        chart = out.get("chart_data", None)
        return {"text": text, "chart": chart}
    except Exception as e:
        return {"text": f"Критическая ошибка парсинга: {e}\nСырой ответ: {response_json}", "chart": None}

def ask_agent(prompt: str, session_id: str, url: str, debug: bool) -> dict:
    headers = {"x-session-id": session_id}
    payload = {"prompt": prompt, "sessionId": session_id}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        raw = r.json()
        if debug:
            st.sidebar.subheader("Сырой ответ JSON")
            st.sidebar.json(raw)
        return parse_n8n_response(raw)
    except requests.exceptions.RequestException as e:
        return {"text": f"Ошибка подключения/таймаута: {e}", "chart": None}
    except Exception as e:
        return {"text": f"Неожиданная ошибка: {e}", "chart": None}

def display_chart(spec, debug: bool = False):
    """Рендер только bar_chart и line_chart (PoC)."""
    try:
        if not spec:
            return
        data = spec.get("data")
        x_col = spec.get("x_column")
        y_col = spec.get("y_column")
        chart_type = (spec.get("type") or "bar_chart").lower()

        if not (data and x_col and y_col):
            st.error("Ошибка: неполная структура chart_data (ожидаю data/x_column/y_column).")
            return

        # data: list[dict] или dict -> DataFrame
        df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)

        # приводим Y к числу
        if y_col not in df.columns or x_col not in df.columns:
            st.error("Ошибка: указанные колонки для графика не найдены в данных.")
            return

        df[y_col] = (
            df[y_col]
            .astype(str)
            .str.replace("\u00A0", "", regex=False)  # NBSP
            .str.replace("%", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df[y_col] = pd.to_numeric(df[y_col], errors="coerce")
        df = df.dropna(subset=[y_col])
        if df.empty:
            st.warning("Данные для графика пустые после очистки.")
            return

        category_order = df[x_col].tolist()

        if chart_type == "line_chart":
            fig = px.line(df, x=x_col, y=y_col, markers=True)
        else:  # bar_chart по умолчанию
            fig = px.bar(df, x=x_col, y=y_col)

        fig.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(categoryorder="array", categoryarray=category_order),
        )
        st.plotly_chart(fig, use_container_width=True)

        if debug:
            with st.expander("Данные графика"):
                st.dataframe(df)
    except Exception as e:
        st.error(f"Не удалось построить график: {e}")

def append_assistant(text: str, chart):
    ss.messages.append({"role": "assistant", "content": text, "chart": chart})

# ================== САЙДБАР ==================
with st.sidebar:
    st.subheader("Настройки Агента")
    st.selectbox("Модель", ["Gemini (через n8n)"], disabled=True)
    st.text_area("Системные инструкции", "Ты — полезный аналитический AI-агент...", height=100, disabled=True)
    st.slider("Температура", 0.0, 1.0, 0.7, disabled=True)

    with st.expander("Дополнительные настройки", expanded=False):
        url_input = st.text_input("Webhook URL", value=N8N_URL)
        ss.debug_mode = st.checkbox("Показывать сырой ответ JSON", value=ss.debug_mode)
        st.caption("Команды: `/clear` — очистка истории.")
    st.caption(f"Session: {ss.session_id}")

    if ss.pending:
        if st.button("⛔ Отменить запрос"):
            ss.pending = False
            ss.pending_prompt = ""
            append_assistant("Запрос отменён пользователем.", None)
            st.rerun()

    if st.button("🧹 Новый чат / очистить всё"):
        ss.session_id = str(uuid.uuid4())
        ss.messages = [{"role": "assistant", "content": "История чата очищена."}]
        ss.pending = False
        ss.pending_prompt = ""
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
        except Exception:
            pass
        st.rerun()

# ================== LAZY FETCH (без «тени», устойчивый) ==================
if ss.pending and ss.pending_prompt and not ss.fetch_in_progress:
    ss.fetch_in_progress = True
    try:
        with st.chat_message("assistant"):
            with st.spinner("Анализирую данные..."):
                resp = ask_agent(ss.pending_prompt, ss.session_id, url_input, ss.debug_mode)
        append_assistant(resp.get("text", "_Пустой ответ от агента_"), resp.get("chart"))
    except Exception as e:
        append_assistant(f"Ошибка запроса: {e}", None)
    finally:
        ss.pending = False
        ss.pending_prompt = ""
        ss.fetch_in_progress = False
        st.rerun()

# ================== РЕНДЕР ИСТОРИИ ==================
for msg in ss.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart"):
            display_chart(msg["chart"], debug=ss.debug_mode)

# ================== ВВОД ПОЛЬЗОВАТЕЛЯ ==================
prompt = st.chat_input("Ваш вопрос...")
if prompt:
    if prompt.strip() == "/clear":
        ss.messages = [{"role": "assistant", "content": "История чата очищена."}]
        ss.pending = False
        ss.pending_prompt = ""
        st.rerun()
    else:
        ss.messages.append({"role": "user", "content": prompt})
        ss.pending = True
        ss.pending_prompt = prompt
        st.rerun()
