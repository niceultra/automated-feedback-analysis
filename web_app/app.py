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
    /* 1. Навигация и Sidebar */
    [data-testid="stSidebar"] {
        min-width: 200px;
        max-width: 250px;
        background-color: #161b22; /* Темный оттенок для sidebar */
    }

    /* Убираем красные точки и стилизуем активный пункт */
    .stRadio [data-testid="stWidgetLabel"] { display: none; }
    div[role="radiogroup"] label {
        background: transparent;
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 5px;
        transition: 0.3s;
    }
    div[role="radiogroup"] label:hover {
        background: rgba(255, 255, 255, 0.05);
    }

    /* 2. Компоненты управления (Кнопка и Инпуты) */
    .stButton>button {
        background-color: #3f51b5 !important; /* Глубокий индиго */
        color: white;
        border-radius: 12px !important; /* Большее скругление */
        border: none;
        padding: 0.6rem 1.5rem;
        font-weight: 500;
        width: auto !important; /* Кнопка не на всю ширину */
    }

    /* Выравнивание высоты блоков */
    [data-testid="stVerticalBlock"] > div:has(div.stContainer) {
        height: 100%;
    }
    .main-card {
        min-height: 250px; /* Фиксированная высота для симметрии */
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    /* 3. Зона загрузки (Drop-zone) */
    [data-testid="stFileUploadDropzone"] {
        border: 2px dashed #3f51b5 !important;
        background: #0d1117;
        border-radius: 15px;
    }

    /* 4. Таблица (Padding и Zebra) */
    .styled-table {
        border-collapse: collapse;
        margin: 25px 0;
        font-size: 0.9em;
        width: 100%;
        border-radius: 8px;
        overflow: hidden;
    }
    </style>
    """, unsafe_allow_html=True)


# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    """Цветовая индикация тональности для таблицы"""
    if val == 2 or val == 'Positive':
        color = '#2e7d32'  # Зеленый
    elif val == 1 or val == 'Negative':
        color = '#d32f2f'  # Красный
    else:
        color = '#757575'  # Серый
    return f'background-color: {color}; color: white; border-radius: 4px; padding: 2px 5px;'

# --- БОКОВАЯ ПАНЕЛЬ (SIDEBAR) ---
with st.sidebar:
    st.title("📂 InsightCopy AI")
    page = st.radio("Навигация", ["🏠 Главная", "📈 Аналитика", "ℹ️ О проекте"])
    st.divider()

# --- СТРАНИЦА: ГЛАВНАЯ ---
if page == "🏠 Главная":
    st.title("InsightCopy AI")
    st.markdown("<p style='opacity: 0.7;'>Аналитика маркетплейсов на базе BERT</p>", unsafe_allow_html=True)

    # Загружаем данные
    product_df = get_all_products()
    # UX-редактура: Переименовываем столбцы для пользователя
    display_df = product_df.rename(columns={
        'nm_id': 'ID Товара',
        'product_name': 'Наименование',
        'category': 'Категория',
        'sentiment_score': 'Тональность'  # Допустим, у нас есть эта колонка
    })

    # ГЛАВНЫЙ РЯД: Поиск и Загрузка
    col_input, col_upload, col_stats = st.columns([1.5, 1.5, 1])

    with col_input:
        with st.container(border=True):
            st.markdown("#### 🔎 Мгновенный анализ")
            product_options = display_df.apply(lambda x: f"{x['Наименование']} ({x['ID Товара']})", axis=1).tolist()

            selected_option = st.selectbox(
                "Выберите товар:",
                options=[""] + product_options,
                label_visibility="collapsed",
                placeholder="Поиск по названию или ID..."
            )
            st.write(" ")  # Воздух
            if st.button("ПОЛУЧИТЬ АНАЛИТИКУ"):
                if selected_option:
                    st.session_state.current_sku = selected_option.split('(')[-1].replace(')', '')
                else:
                    st.toast("Сначала выберите товар", icon="⚠️")

    with col_upload:
        with st.container(border=True):
            st.markdown("#### ⚙️ Ваши данные")
            st.file_uploader(
                "Перетащите отчет сюда",
                type=['csv', 'xlsx'],
                label_visibility="collapsed"
            )
            st.caption("Поддерживаются форматы WB и OZON")

    with col_stats:
        with st.container(border=True):
            st.markdown("#### 📊 Сводка")
            st.metric("Товаров в базе", len(product_df))
            st.metric("Точность BERT", "94%")

    # БЛОК ОБЗОРА БАЗЫ
    st.write("---")
    st.subheader("📦 Мониторинг каталога")

    if not display_df.empty:
        # Применяем стилизацию таблицы (Zebra stripes и Sentiment Visuals)
        # В Streamlit st.dataframe поддерживает pandas styler
        styled_df = display_df.head(15).style.applymap(
            color_sentiment, subset=['Тональность'] if 'Тональность' in display_df.columns else []
        )

        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        # Пустое состояние (Empty State)
        st.info("🔍 В базе пока нет данных. Загрузите файл или подключите API.")


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