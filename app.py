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
    """Рендер графика через Plotly, устойчив к категориальной X и разным форматам данных."""
    try:
        if not chart_info:
            return

        data = chart_info.get("data")
        x_col = chart_info.get("x_column")
        y_col = chart_info.get("y_column")
        chart_type = (chart_info.get("type") or "").lower()

        if not (data and x_col and y_col):
            st.error("Ошибка: неполная структура chart_data (ожидаю data/x_column/y_column).")
            return

        # data может быть list[dict] или dict
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        else:
            df = pd.DataFrame(data)

        if x_col not in df.columns or y_col not in df.columns:
            st.error("Ошибка: указанные колонки для графика не найдены в данных.")
            return

        # Чистим и приводим Y к числу
        df[y_col] = (
            df[y_col].astype(str)
            .str.replace(" ", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        df[y_col] = pd.to_numeric(df[y_col], errors="coerce")
        df = df.dropna(subset=[y_col])

        if df.empty:
            st.warning("Данные для графика пустые после очистки.")
            return

        # Сохраняем порядок категорий как в данных
        category_order = df[x_col].tolist()

        if chart_type == "line_chart":
            fig = px.line(df, x=x_col, y=y_col, markers=True)
        else:  # по умолчанию столбчатая
            fig = px.bar(df, x=x_col, y=y_col)

        fig.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(categoryorder="array", categoryarray=category_order),
        )

        st.plotly_chart(fig, use_container_width=True)

        if debug:
            with st.expander("Данные, переданные в график"):
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
        st.session_state.session_id = str(uuid.uuid4())  # новый поток на стороне n8n
        st.session_state.messages = [{"role": "assistant", "content": "История чата очищена."}]
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
        except Exception:
            pass
        st.rerun()  # мгновенный перезапуск (без F5)

# ================== ИНИЦИАЛИЗАЦИЯ И ИСТОРИЯ ЧАТА ==================
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Кого будем увольнять сегодня?"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "chart" in msg and msg.get("chart"):
            display_chart(msg["chart"], debug=debug_mode)

# ================== ОБРАБОТКА НОВОГО ЗАПРОСА ==================
if prompt := st.chat_input("Ваш вопрос..."):
    if prompt.strip() == "/clear":
        st.session_state.messages = [{"role": "assistant", "content": "История чата очищена."}]
        st.rerun()
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Анализирую данные..."):
                response_data = ask_agent(
                    prompt,
                    st.session_state.session_id,
                    url_input,
                    debug_mode
                )

            response_text = response_data.get("text", "_Пустой ответ от агента_")
            chart_data = response_data.get("chart")

            st.markdown(response_text)
            if chart_data:
                display_chart(chart_data, debug=debug_mode)

        # сохраняем ответ в историю для последующих перерисовок
        st.session_state.messages.append({
            "role": "assistant",
            "content": response_text,
            "chart": chart_data
        })
