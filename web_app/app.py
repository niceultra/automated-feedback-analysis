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


# --- СТИЛИЗАЦИЯ ПОД МИНИМАЛИЗМ ---
st.markdown("""
    <style>
    /* Убираем лишние отступы сверху */
    .block-container { padding-top: 2rem; }

    /* Чистый Sidebar без лишних линий */
    [data-testid="stSidebar"] {
        background-color: #111418;
        border-right: 1px solid #1e2227;
    }

    /* Кнопка: Минимум цвета, максимум стиля */
    .stButton>button {
        width: 100%;
        background-color: #2e343d !important;
        color: #ffffff;
        border: 1px solid #4a505e !important;
        border-radius: 8px !important;
        transition: 0.2s;
    }
    .stButton>button:hover {
        border-color: #3f51b5 !important;
        background-color: #1e2227 !important;
    }

    /* Таблица: Делаем её "невидимой" и чистой */
    [data-testid="stDataFrame"] {
        border: none !important;
    }

    /* Убираем жирные заголовки контейнеров */
    h3, h4 {
        font-weight: 400 !important;
        letter-spacing: -0.02em;
        opacity: 0.9;
    }
    </style>
    """, unsafe_allow_html=True)

# --- УПРАВЛЕНИЕ В SIDEBAR (как у профессиональных демо) ---
with st.sidebar:
    st.title("InsightCopy")
    st.caption("v 2.1 — Sentiment Analysis")

    st.write("---")

    # ПЕРЕНОСИМ УПРАВЛЕНИЕ СЮДА
    st.markdown("### Анализ")
    product_options = display_df.apply(lambda x: f"{x['Наименование']} ({x['ID Товара']})", axis=1).tolist()
    selected_option = st.selectbox("Выберите артикул из базы:", [""] + product_options)

    if st.button("Запустить анализ"):
        if selected_option:
            st.session_state.current_sku = selected_option.split('(')[-1].replace(')', '')

    st.write("---")
    st.markdown("### Загрузка")
    st.file_uploader("Загрузить свой отчет", type=['csv', 'xlsx'])

# --- ОСНОВНАЯ ЧИСТАЯ ОБЛАСТЬ ---
if 'current_sku' not in st.session_state:
    # Приветственный экран, если ничего не выбрано
    st.title("Мониторинг каталога")

    # Горизонтальные метрики без рамок
    m1, m2, m3 = st.columns(3)
    m1.metric("Всего товаров", len(product_df))
    m2.metric("Активность", "Высокая")
    m3.metric("Точность", "94%")

    st.write("---")

    # Чистая таблица
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
else:
    # Экран с результатами (только аналитика)
    sku = st.session_state.current_sku
    st.title(f"Аналитика: {sku}")

    summary = get_summary(sku)
    if summary:
        with st.container():
            st.markdown(f"<div style='padding: 20px; background: #1a1c23; border-radius: 15px;'>{summary}</div>",
                        unsafe_allow_html=True)

    if st.button("← Вернуться к списку"):
        del st.session_state.current_sku
        st.rerun()

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
        styled_df = display_df.head(15).style.map(
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