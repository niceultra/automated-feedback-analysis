import streamlit as st
import pandas as pd
import psycopg2
import streamlit.components.v1 as components

# --- ДАННЫЕ ПОДКЛЮЧЕНИЯ ---
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=6432,
        sslmode='require'
    )

def get_product_analytics(nm_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT summary_text, chart_html FROM product_summary WHERE nm_id = %s", (str(nm_id),))
        result = cursor.fetchone()
        conn.close()
        return result if result else (None, None)
    except:
        return None, None

def get_reviews(nm_id):
    try:
        conn = get_db_connection()
        query = f"SELECT review_text, sentiment, confidence FROM reviews WHERE nm_id = '{nm_id}'"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except:
        return None

# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    if val == 2 or val == 'Positive': return 'color: #4caf50; font-weight: bold;'
    if val == 1 or val == 'Negative': return 'color: #f44336; font-weight: bold;'
    return 'color: #9e9e9e;'

# --- СТРАНИЦА: АНАЛИТИКА ---
st.title("Результаты анализа")

if st.session_state.get('current_sku'):
    current_sku = st.session_state.current_sku
    summary_text, chart_html = get_product_analytics(current_sku)

    if summary_text:
        st.markdown(f"#### 📊 Отчет по товару: {current_sku}")

        # 1. Текстовое резюме
        st.markdown(f'<div class="result-box">{summary_text}</div>', unsafe_allow_html=True)

        # 2. Визуализация (График из БД)
        if chart_html:
            st.markdown('<div class="section-title">📈 Распределение мнений</div>', unsafe_allow_html=True)
            components.html(chart_html, height=450, scrolling=True)

        # 3. Исходные отзывы
        with st.expander("🔍 Посмотреть детальные отзывы и уверенность модели"):
            reviews_df = get_reviews(current_sku)
            if reviews_df is not None and not reviews_df.empty:
                styled_reviews = reviews_df.style.map(color_sentiment, subset=['sentiment'])
                st.dataframe(styled_reviews, use_container_width=True)
            else:
                st.info("Отзывы не найдены.")
    else:
        st.warning(f"Аналитика для артикула {current_sku} находится в обработке.")
else:
    st.info("⬅️ Выберите товар на главной странице для просмотра аналитики.")
    if st.button("Вернуться на главную"):
        st.switch_page("pages/1_Главная.py")