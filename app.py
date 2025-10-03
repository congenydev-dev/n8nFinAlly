import streamlit as st
import requests
import uuid
import pandas as pd
import plotly.express as px

# ================== КОНФИГУРАЦИЯ ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
# TIMEOUT = (connect_timeout, read_timeout)
TIMEOUT = (10, 120)

# ================== НАСТРОЙКА СТРАНИЦЫ ==================
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")

# ================== СЕССИЯ ==================
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]

# ================== ФУНКЦИИ ==================
def parse_n8n_response(response_json: list | dict) -> dict:
    """Достаём текст и параметры графика из ответа n8n."""
    try:
        data = response_json[0] if isinstance(response_json, list) and response_json else response_json
        output_data = data.get("output", {}) if isinstance(data, dict) else {}
        text = output_data.get("analytical_report", "Ошибка: не удалось извлечь текстовый отчёт из ответа.")
        chart = output_data.get("chart_data", None)
        return {"text": text, "chart": chart}
    except Exception as e:
        return {
            "text": f"Критическая ошибка при парсинге ответа: {e}\nСырой ответ: {str(response_json)}",
            "chart": None,
        }

def ask_agent(prompt: str, session_id: str, url: str, debug: bool) -> dict:
    """Отправляем запрос в n8n и возвращаем распарсенный ответ."""
    headers = {"x-session-id": session_id}
    payload = {"prompt": prompt, "sessionId": session_id}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        raw_response = response.json()
        if debug:
            st.sidebar.subheader("Сырой ответ JSON")
            st.sidebar.json(raw_response)
        return parse_n8n_response(raw_response)
    except requests.exceptions.RequestException as e:
        return {"text": f"Ошибка подключения или таймаута: {e}", "chart": None}
    except Exception as e:
        return {"text": f"Неожиданная ошибка: {e}", "chart": None}

def display_chart(chart_info, debug: bool = False):
    """Рендер одного графика через Plotly. Поддержка типов:
       bar_chart, line_chart, area_chart, scatter, pie, histogram, box."""
    try:
        if not chart_info:
            return

        data = chart_info.get("data")
        x_col = chart_info.get("x_column")
        y_col = chart_info.get("y_column")
        chart_type = (chart_info.get("type") or "bar_chart").lower()

        if not (data and x_col and y_col):
            st.error("Ошибка: неполная структура chart_data (ожидаю data/x_column/y_column).")
            return

        # data может быть list[dict] или dict
        df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)

        # y_column: строка или список строк (на будущее для мультисерий)
        y_cols = [y_col] if isinstance(y_col, str) else list(y_col)

        # привести числовые столбцы (только Y) к числу
        for yc in y_cols:
            if yc in df.columns:
                df[yc] = (
                    df[yc].astype(str)
                    .str.replace("\u00A0", "", regex=False)  # NBSP
                    .str.replace("%", "", regex=False)
                    .str.replace(" ", "", regex=False)
                    .str.replace(",", ".", regex=False)
                )
                df[yc] = pd.to_numeric(df[yc], errors="coerce")

        # порядок категорий как в данных
        category_order = df[x_col].tolist() if x_col in df.columns else None

        # === отрисовка по типу ===
        if chart_type == "line_chart":
            if len(y_cols) == 1:
                fig = px.line(df, x=x_col, y=y_cols[0], markers=True)
            else:
                long_df = df[[x_col] + [c for c in y_cols if c in df.columns]].melt(
                    id_vars=[x_col], var_name="series", value_name="value"
                )
                fig = px.line(long_df, x=x_col, y="value", color="series", markers=True)

        elif chart_type == "area_chart":
            if len(y_cols) == 1:
                fig = px.area(df, x=x_col, y=y_cols[0])
            else:
                long_df = df[[x_col] + [c for c in y_cols if c in df.columns]].melt(
                    id_vars=[x_col], var_name="series", value_name="value"
                )
                fig = px.area(long_df, x=x_col, y="value", color="series")

        elif chart_type == "scatter":
            yc = y_cols[0]
            fig = px.scatter(df, x=x_col, y=yc)

        elif chart_type == "pie":
            yc = y_cols[0]
            fig = px.pie(df, names=x_col, values=yc, hole=0.0)

        elif chart_type == "histogram":
            yc = y_cols[0]
            fig = px.histogram(df, x=yc)

        elif chart_type == "box":
            yc = y_cols[0]
            if x_col in df.columns:
                fig = px.box(df, x=x_col, y=yc)
            else:
                fig = px.box(df, y=yc)

        else:  # bar_chart по умолчанию
            if len(y_cols) == 1:
                fig = px.bar(df, x=x_col, y=y_cols[0])
            else:
                long_df = df[[x_col] + [c for c in y_cols if c in df.columns]].melt(
                    id_vars=[x_col], var_name="series", value_name="value"
                )
                barmode = "stack" if chart_info.get("stacked") else "group"
                fig = px.bar(long_df, x=x_col, y="value", color="series", barmode=barmode)

        fig.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(categoryorder="array", categoryarray=category_order) if category_order else dict(),
        )
        st.plotly_chart(fig, use_container_width=True)

        if debug:
            with st.expander("Данные графика"):
                st.dataframe(df)
    except Exception as e:
        st.error(f"Не удалось построить график: {e}")

# ================== UI БОКОВАЯ ПАНЕЛЬ ==================
with st.sidebar:
    st.subheader("Настройки Агента")
    st.selectbox("Модель", ["Gemini (через n8n)"], disabled=True)
    st.text_area("Системные инструкции", "Ты — полезный аналитический AI-агент...", height=100, disabled=True)
    st.slider("Температура", 0.0, 1.0, 0.7, disabled=True)

    with st.expander("Дополнительные настройки", expanded=False):
        url_input = st.text_input("Webhook URL", value=N8N_URL)
        debug_mode = st.checkbox("Показывать сырой ответ JSON", value=False)
        st.caption("Команды в чате: `/clear` — очистка истории.")

    st.caption(f"Session: {st.session_state.session_id}")

    # === КНОПКА ПОЛНОЙ ОЧИСТКИ СЕССИИ ===
    if st.button("🧹 Новый чат / очистить всё"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = [{"role": "assistant", "content": "История чата очищена."}]
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
        except Exception:
            pass
        st.rerun()

# ================== LAZY FETCH ОТВЕТА (чтобы не было «тени») ==================
def need_reply() -> bool:
    if not st.session_state.messages:
        return False
    return st.session_state.messages[-1]["role"] == "user"

if need_reply():
    with st.chat_message("assistant"):
        with st.spinner("Анализирую данные..."):
            last_user_prompt = st.session_state.messages[-1]["content"]
            response_data = ask_agent(
                last_user_prompt,
                st.session_state.session_id,
                url_input,
                debug_mode,
            )
    st.session_state.messages.append({
        "role": "assistant",
        "content": response_data.get("text", "_Пустой ответ от агента_"),
        "chart": response_data.get("chart")
    })
    st.rerun()

# ================== РЕНДЕР ИСТОРИИ ==================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart"):
            display_chart(msg["chart"], debug=debug_mode)

# ================== ОБРАБОТКА НОВОГО ЗАПРОСА ==================
prompt = st.chat_input("Ваш вопрос...")
if prompt:
    if prompt.strip() == "/clear":
        st.session_state.messages = [{"role": "assistant", "content": "История чата очищена."}]
        st.rerun()
    else:
        # Только записываем пользователя и моментально перерисовываем — ответ подтянется в lazy fetch
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()
