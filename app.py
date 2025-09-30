import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import uuid
import streamlit.components.v1 as components

# ---------- Page ----------
st.set_page_config(page_title="Аналитический AI-агент", layout="wide")

# ---------- Config ----------
N8N_WEBHOOK_URL = "https://finally.app.n8n.cloud/webhook/550ca24c-1f7c-47fd-8f44-8028fb7ecd0d"

# ---------- Helpers ----------
def _to_df(data) -> pd.DataFrame:
    if isinstance(data, list):
        return pd.DataFrame(data)
    elif isinstance(data, dict):
        return pd.DataFrame([data])
    return pd.DataFrame()

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

def display_chart(chart_info: dict, key: str | None = None):
    """
    Поддерживаемые типы: bar_chart, line_chart
    Ожидаемые поля: data(list|dict), x_column(str), y_column(str|list[str])
    """
    try:
        df = _to_df(chart_info.get("data"))
        chart_type = chart_info.get("type", "bar_chart")
        x_col = chart_info.get("x_column")
        y_col = chart_info.get("y_column")

        if not _require_fields(chart_info, ["x_column", "y_column"]):
            return

        title = chart_info.get("title") or (f"{y_col} по {x_col}" if y_col and x_col else "Chart")

        if chart_type == "bar_chart":
            fig = px.bar(df, x=x_col, y=y_col, title=title, template="plotly_white", barmode="group")
        elif chart_type == "line_chart":
            fig = px.line(df, x=x_col, y=y_col, title=title, template="plotly_white", markers=True)
        else:
            st.warning("Тип графика не поддерживается (разрешены: bar_chart, line_chart).")
            return

        st.plotly_chart(fig, use_container_width=True, key=key)
        if chart_info.get("show_table"):
            st.dataframe(df, use_container_width=True, key=f"{key}-table" if key else None)

    except Exception as e:
        st.error(f"Не удалось отобразить график. Ошибка: {e}")

def scroll_to_bottom():
    # лёгкая автопрокрутка к последнему сообщению
    components.html(
        """
        <script>
        (function(){
          try{
            const p = window.parent;
            const main = p.document.querySelector('section.main') || p.document.body;
            main.scrollTo({ top: main.scrollHeight, behavior: 'instant' });
          }catch(e){}
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )

# ---------- State ----------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Какие данные проанализируем сегодня?"}]

# ---------- UI ----------
st.title("Аналитический AI-агент")
st.markdown("Здравствуйте! Я ваш аналитический AI-агент. Попросите меня визуализировать данные.")
st.divider()

# История (с уникальными ключами для графиков)
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "chart" in message:
            display_chart(message["chart"], key=f"chart-{i}")

# автопрокрутка к последнему сообщению
scroll_to_bottom()

# Ввод
if prompt := st.chat_input("Спросите что-нибудь о ваших данных..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        with st.spinner('Анализирую...'):
            json_response = fetch_from_n8n(prompt.strip(), st.session_state.session_id)

        text_response = json_response.get("text_response", "Получен пустой ответ от сервера.")
        chart_info = json_response.get("chart_data")

        assistant_message = {"role": "assistant", "content": text_response}
        if isinstance(chart_info, dict) and chart_info.get("data"):
            assistant_message["chart"] = chart_info

        st.session_state.messages.append(assistant_message)

        # перерисуем через историю (чтобы не дублировать график и не ловить конфликт ID)
        st.experimental_rerun()

    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка подключения к workflow: {e}")
    except requests.exceptions.JSONDecodeError:
        st.error("Ответ сервера не JSON.")
    except Exception as e:
        st.error(f"Произошла ошибка: {e}")
