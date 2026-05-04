import streamlit as st
import pandas as pd
import psycopg2
import streamlit.components.v1 as components
from PIL import Image

# 1. Настройка страницы
st.set_page_config(
    page_title="InsightCopy AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ---
if 'page' not in st.session_state:
    st.session_state.page = "Главная"
if 'current_sku' not in st.session_state:
    st.session_state.current_sku = None
if 'current_category' not in st.session_state:
    st.session_state.current_category = None

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
    """Получает и текст резюме, и HTML-код графика"""
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
        # Выбираем текст, тональность и уверенность модели
        query = f"SELECT review_text, sentiment, confidence FROM reviews WHERE nm_id = '{nm_id}'"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except:
        return None


def get_all_products():
    try:
        conn = get_db_connection()
        # Используем обновленные названия колонок: category_name
        df = pd.read_sql("SELECT nm_id, category_name, product_name, product_url FROM products", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame(columns=['nm_id', 'category_name', 'product_name', 'product_url'])


# --- КАСТОМНЫЙ CSS ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; }
    .result-box {
        padding: 25px;
        border-radius: 15px;
        background-color: #1a1c23;
        border-left: 5px solid #3f51b5;
        line-height: 1.6;
        margin-bottom: 20px;
    }
    .section-title {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    /* Стилизация метрик для чистого вида */
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    </style>
    """, unsafe_allow_html=True)


# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    # Соответствие согласно Ledger: 1-neg, 2-pos, 0-neutral
    if val == 2 or val == 'Positive': return 'color: #4caf50; font-weight: bold;'
    if val == 1 or val == 'Negative': return 'color: #f44336; font-weight: bold;'
    return 'color: #9e9e9e;'


# --- ПОДГОТОВКА ДАННЫХ ---
product_df = get_all_products()

# --- БОКОВАЯ ПАНЕЛЬ (SIDEBAR) ---
with st.sidebar:
    st.title("📂 InsightCopy AI")
    st.caption("Sentiment Analysis Dashboard")
    st.divider()

    st.markdown("### Навигация")
    if st.button("🏠 Главная", use_container_width=True):
        st.session_state.page = "Главная"
    if st.button("📈 Аналитика", use_container_width=True):
        st.session_state.page = "Аналитика"
    if st.button("ℹ️ О проекте", use_container_width=True):
        st.session_state.page = "О проекте"

# --- СТРАНИЦА: ГЛАВНАЯ ---
if st.session_state.page == "Главная":
    st.title("Мониторинг каталога")
    st.markdown("<p style='opacity: 0.6;'>Аналитическая точность и инсайты вашего бренда</p>", unsafe_allow_html=True)

    # Метрики (оставляем как есть)
    m1, m2, m3 = st.columns(3)
    m1.metric("Товаров в базе", len(product_df))
    m2.metric("Активность системы", "Высокая")
    m3.metric("Точность BERT", "94%", delta="↑ 2%")

    st.divider()

    st.markdown('<div class="section-title">📦 База товаров для анализа</div>', unsafe_allow_html=True)

    search_query = st.text_input("Поиск по категориям", placeholder="Например: Красота", label_visibility="collapsed")

    if not product_df.empty:
        categories = product_df['category_name'].unique()
        if search_query:
            categories = [cat for cat in categories if search_query.lower() in cat.lower()]

        for category in categories:
            with st.expander(f"📦 {category}", expanded=False):
                cat_prods = product_df[product_df['category_name'] == category]
                for _, row in cat_prods.iterrows():
                    # Проверяем, выбран ли этот товар сейчас
                    is_active = st.session_state.current_sku == row['nm_id']
                    button_label = f"✅ {row['product_name']}" if is_active else f"▫️ {row['product_name']}"

                    if st.button(button_label, key=f"btn_{row['nm_id']}", use_container_width=True):
                        st.session_state.current_sku = row['nm_id']
                        st.session_state.current_category = category
                        st.rerun()  # Перезапускаем, чтобы показать кнопку перехода

    # --- УЛУЧШЕНИЕ: КНОПКА ПЕРЕХОДА К АНАЛИТИКЕ ---
    if st.session_state.current_sku:
        st.write("")  # Отступ
        # Находим имя выбранного товара для красоты
        selected_name = product_df[product_df['nm_id'] == st.session_state.current_sku]['product_name'].values[0]

        st.info(f"Выбран товар: **{selected_name}**")

        # Большая кнопка перехода
        if st.button("🚀 Перейти к детальной аналитике", type="primary", use_container_width=True):
            st.session_state.page = "Аналитика"
            st.rerun()

    st.divider()

    # Таблица каталога
    st.subheader("Полный список артикулов")
    if not product_df.empty:
        display_list = product_df[['nm_id', 'product_name', 'category_name']].rename(
            columns={'nm_id': 'ID', 'product_name': 'Наименование', 'category_name': 'Категория'}
        )
        st.dataframe(display_list, use_container_width=True, hide_index=True)

# --- СТРАНИЦА: АНАЛИТИКА ---
elif st.session_state.page == "Аналитика":
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
                    # Применяем цветовое форматирование к тональности
                    styled_reviews = reviews_df.style.map(color_sentiment, subset=['sentiment'])
                    st.dataframe(styled_reviews, use_container_width=True)
                else:
                    st.info("Отзывы не найдены.")
        else:
            st.warning(f"Аналитика для артикула {current_sku} находится в обработке.")
    else:
        st.info("⬅️ Выберите товар на главной странице для просмотра аналитики.")

# --- СТРАНИЦА: О ПРОЕКТЕ ---
elif st.session_state.page == "О проекте":
    st.title("О проекте")
    st.markdown("""
    **InsightCopy AI** — это инструмент для глубокого NLP-анализа отзывов. 
    Мы используем современные архитектуры трансформеров для обеспечения **аналитической точности**.

    **Стек технологий:**
    *   **LLM Core:** Модели семейства BERT для классификации тональности.
    *   **Backend:** PostgreSQL (Managed) для хранения результатов.
    *   **Visuals:** Plotly/D3.js для интерактивных графиков.
    *   **Frontend:** Streamlit для быстрого доступа к инсайтам.
    """)
    st.divider()
    st.image("https://huggingface.co/front/assets/huggingface_logo-noborder.svg", width=80)