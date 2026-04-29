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
def get_all_products():
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=6432, sslmode='require')
        # Предполагаем, что в product_summary или другой таблице есть названия товаров
        df = pd.read_sql("SELECT nm_id, category, product_name FROM product_catalog", conn)
        conn.close()
        return df
    except:
        # Заглушка для теста, если таблицы catalog еще нет
        return pd.DataFrame({
            'nm_id': ['287657449', '3642034', '933351429'],
            'product_name': ['Смартфон X1', 'Наушники Pro', 'Чехол Silicone'],
            'category': ['Электроника', 'Электроника', 'Аксессуары']
        })

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
    st.title("Welcome to InsightCopy AI")
    st.caption("Аналитика тональности и генерация контента на основе отзывов.")

    # 1. ЗАГРУЗКА ДАННЫХ ДЛЯ СПРАВОЧНИКА
    product_df = get_all_products()

    # Создаем список для поиска в формате "Название (Артикул)"
    product_options = product_df.apply(lambda x: f"{x['product_name']} ({x['nm_id']})", axis=1).tolist()

    # --- БЛОК ПОИСКА ---
    with st.container(border=True):
        st.subheader("🔎 Мгновенный анализ")

        # Вместо обычного ввода — выпадающий список с поиском
        selected_option = st.selectbox(
            "Выберите товар из базы или введите название:",
            options=[""] + product_options,
            index=0,
            placeholder="Начните вводить название или артикул..."
        )

        if st.button("ПОЛУЧИТЬ АНАЛИТИКУ", type="primary"):
            if selected_option:
                # Извлекаем nm_id из строки "Название (12345)"
                sku = selected_option.split('(')[-1].replace(')', '')
                st.session_state.current_sku = sku
            else:
                st.warning("Сначала выберите товар из списка.")

    # --- БЛОК РЕЗУЛЬТАТОВ (Появляется здесь же!) ---
    if 'current_sku' in st.session_state:
        st.divider()
        sku = st.session_state.current_sku

        # Получаем данные (те же функции, что были в Аналитике)
        summary = get_summary(sku)

        if summary:
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.markdown(f"### 📊 Результаты для артикула {sku}")
                st.info(summary)
            with col_b:
                st.markdown("### 📈 Метрики")
                st.metric("Тональность", "Позитивная", "+12%")
                if st.button("Открыть детальный отчет"):
                    st.switch_page("страница_аналитики.py")  # Если нужно уйти в детали
        else:
            st.error("Аналитика для этого товара еще не готова.")

    st.write("")

    # --- БЛОК ОБЗОРА БАЗЫ ---
    st.markdown("### 📦 Доступно в базе данных")

    tab1, tab2 = st.tabs(["Все товары", "По категориям"])

    with tab1:
        # Показываем таблицу, чтобы пользователь понимал масштаб
        st.dataframe(
            product_df[['nm_id', 'product_name', 'category']],
            use_container_width=True,
            hide_index=True
        )

    with tab2:
        # Группировка для понимания структуры
        cat_counts = product_df['category'].value_counts()
        st.bar_chart(cat_counts)
        st.write(f"Всего категорий: **{len(cat_counts)}**")


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