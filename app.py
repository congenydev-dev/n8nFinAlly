import streamlit as st
import requests
import uuid
import pandas as pd

# ================== КОНФИГ ==================
N8N_URL = "https://finally.app.n8n.cloud/webhook/bf4dd093-bb02-472c-9454-7ab9af97bd1d"
TIMEOUT = (10, 180)  # (connect, read) — чтобы UI не "замирал"

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

def _to_numeric_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.replace("\u00A0", "", regex=False)   # NBSP
         .str.replace("%", "", regex=False)
         .str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False)
         .pipe(pd.to_numeric, errors="coerce")
    )

def display_chart_streamlit(spec, debug: bool = False):
    """Только bar_chart и line_chart. Нативные st.bar_chart/st.line_chart."""
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

        df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)
        if x_col not in df.columns or y_col not in df.columns:
            st.error("Ошибка: указанные колонки для графика не найдены в данных.")
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

        if debug:
            with st.expander("Данные графика"):
                st.dataframe(df)
    except Exception as e:
        st.error(f"Не удалось построить график: {e}")

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
            # Заменим «ожидающий» месседж, если он есть
            if ss.messages and ss.messages[-1].get("pending"):
                ss.messages[-1] = {"role": "assistant", "content": "Запрос отменён пользователем.", "chart": None}
            else:
                ss.messages.append({"role": "assistant", "content": "Запрос отменён пользователем.", "chart": None})
            st.rerun()

    if st.button("🧹 Новый чат / очистить всё"):
        ss.session_id = str(uuid.uuid4())
        ss.messages = [{"role": "assistant", "content": "История чата очищена."}]
        ss.pending = False
        ss.pending_prompt = ""
        try:
            st.cache_data.clear(); st.cache_resource.clear()
        except Exception:
            pass
        st.rerun()

# ================== LAZY FETCH (без «тени»: только история) ==================
if ss.pending and ss.pending_prompt and not ss.fetch_in_progress:
    ss.fetch_in_progress = True
    try:
        resp = ask_agent(ss.pending_prompt, ss.session_id, url_input, ss.debug_mode)
        text = resp.get("text", "_Пустой ответ от агента_")
        chart = resp.get("chart")
        # ВАЖНО: заменяем последнюю «ожидающую» запись, а не добавляем новую
        if ss.messages and ss.messages[-1].get("pending"):
            ss.messages[-1] = {"role": "assistant", "content": text, "chart": chart}
        else:
            ss.messages.append({"role": "assistant", "content": text, "chart": chart})
    except Exception as e:
        if ss.messages and ss.messages[-1].get("pending"):
            ss.messages[-1] = {"role": "assistant", "content": f"Ошибка запроса: {e}", "chart": None}
        else:
            ss.messages.append({"role": "assistant", "content": f"Ошибка запроса: {e}", "chart": None})
    finally:
        ss.pending = False
        ss.pending_prompt = ""
        ss.fetch_in_progress = False
        st.rerun()

# ================== РЕНДЕР ИСТОРИИ ==================
for msg in ss.messages:
    with st.chat_message(msg["role"]):
        if msg.get("pending"):
            # ОДНО "ожидающее" сообщение — без реального контента (никаких дублей)
            st.write("… Анализирую данные …")
            with st.spinner(""):
                pass
        else:
            st.markdown(msg["content"])
            if msg.get("chart"):
                display_chart_streamlit(msg["chart"], debug=ss.debug_mode)

# ================== ВВОД ПОЛЬЗОВАТЕЛЯ ==================
prompt = st.chat_input("Ваш вопрос...")
if prompt:
    if prompt.strip() == "/clear":
        ss.messages = [{"role": "assistant", "content": "История чата очищена."}]
        ss.pending = False
        ss.pending_prompt = ""
        st.rerun()
    else:
        # 1) записываем пользователя
        ss.messages.append({"role": "user", "content": prompt})
        # 2) добавляем ПЛЕЙСХОЛДЕР ассистента (pending=True)
        ss.messages.append({"role": "assistant", "content": "", "pending": True})
        # 3) запускаем фетч
        ss.pending = True
        ss.pending_prompt = prompt
        st.rerun()
