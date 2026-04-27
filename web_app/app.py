import streamlit as st
import pandas as pd
import psycopg2
from PIL import Image

# 1. Настройка страницы
st.set_page_config(
    page_title="InsightCopy AI — Аналитика",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ДАННЫЕ ПОДКЛЮЧЕНИЯ  ---
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_summary(nm_id):
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=6432,
                                sslmode='require')
        cursor = conn.cursor()
        cursor.execute("SELECT summary_text FROM product_summary WHERE nm_id = %s", (nm_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except:
        return None


def get_reviews(nm_id):
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=6432,
                                sslmode='require')
        df = pd.read_sql(f"SELECT review_text FROM reviews WHERE nm_id = {nm_id}", conn)
        conn.close()
        return df
    except:
        return None


# --- КАСТОМНЫЙ CSS (Для стиля как на картинке) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button {
        background-color: #00c853;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 0.5rem 2rem;
    }
    .card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- БОКОВАЯ ПАНЕЛЬ (SIDEBAR) ---
with st.sidebar:
    st.title("📂 InsightCopy AI")
    page = st.radio("Навигация", ["🏠 Главная", "📈 Аналитика", "ℹ️ О проекте"])
    st.divider()
    st.caption("Пользователь: Mary Gitlam")

# --- СТРАНИЦА: ГЛАВНАЯ ---
if page == "🏠 Главная":
    st.title("Welcome to InsightCopy AI: E-commerce Sentiment Hub")
    st.caption("Агрегируйте, анализируйте и генерируйте контент на основе отзывов покупателей.")
    st.write("")  # Небольшой отступ

    # Используем нативный контейнер с рамкой вместо HTML-карточек
    with st.container(border=True):
        st.subheader("Начать анализ (SKU, категория или бренд)")
        sku_input = st.text_input(
            "Введите артикул",
            placeholder="Например, 287657449...",
            label_visibility="collapsed"  # Скрываем текст над полем для чистоты дизайна
        )
        # type="primary" сделает кнопку яркой (зеленой или синей в зависимости от темы)
        if st.button("START ANALYSIS", type="primary"):
            if sku_input:
                st.session_state.current_sku = sku_input
                st.success(f"Артикул {sku_input} принят. Теперь перейдите во вкладку Аналитика.")

    st.write("")  # Еще отступ

    # Две карточки снизу в колонках
    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("### 🔍 ПОИСК В БАЗЕ")
            st.write("Доступ к готовой аналитике для топ-1000 товаров и категорий.")
            st.button("ОБЗОР КАТЕГОРИЙ", use_container_width=True)

    with col2:
        with st.container(border=True):
            st.markdown("### ⚙️ АНАЛИЗ ВАШИХ ДАННЫХ")
            st.write("Загрузите свой .xlsx или .csv файл для обработки BERT.")
            st.file_uploader("Загрузить файл", type=['csv', 'xlsx'], label_visibility="collapsed")

# --- СТРАНИЦА: АНАЛИТИКА ---
elif page == "📈 Аналитика":
    st.title("Результаты анализа")

    # Берем SKU из сессии или просим ввести
    current_sku = st.text_input("Текущий артикул:", value=st.session_state.get('current_sku', '287657449'))

    if current_sku:
        summary = get_summary(current_sku)
        if summary:
            st.markdown("### 🤖 Итоговый отчет нейросети")
            st.info(summary)

            with st.expander("Посмотреть исходные отзывы"):
                reviews_df = get_reviews(current_sku)
                if reviews_df is not None:
                    st.dataframe(reviews_df, use_container_width=True)
        else:
            st.warning("Аналитика для данного SKU не найдена.")

# --- СТРАНИЦА: О ПРОЕКТЕ ---
elif page == "ℹ️ О проекте":
    st.title("О проекте")
    st.markdown("""
    Данная система разработана в рамках ВКР и предназначена для автоматизированного анализа тональности отзывов e-commerce.

    **Технологический стек:**
    - **Model:** BERT (Natural Language Processing)
    - **Backend:** Yandex Managed PostgreSQL
    - **Frontend:** Streamlit Framework
    - **Data:** Selenium & BeautifulSoup (Парсинг WB)
    """)
    st.image("https://huggingface.co/front/assets/huggingface_logo-noborder.svg", width=100)