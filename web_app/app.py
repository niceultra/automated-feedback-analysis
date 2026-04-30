import streamlit as st
import pandas as pd
import psycopg2
from PIL import Image

# 1. Настройка страницы в стиле ECharts Gallery
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
# Используем секреты Streamlit для безопасности
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
        # Оборачиваем nm_id в кавычки на случай, если это строка
        df = pd.read_sql(f"SELECT review_text FROM reviews WHERE nm_id = '{nm_id}'", conn)
        conn.close()
        return df
    except:
        return None


def get_all_products():
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=6432,
                                sslmode='require')
        df = pd.read_sql("SELECT nm_id, category, product_name FROM product_catalog", conn)
        conn.close()
        return df
    except:
        # Заглушка для теста, если база недоступна
        return pd.DataFrame({
            'nm_id': ['287657449', '3642034', '933351429'],
            'product_name': ['Смартфон X1', 'Наушники Pro', 'Чехол Silicone'],
            'category': ['Электроника', 'Электроника', 'Аксессуары'],
            'sentiment_score': [2, 0, 1]
        })


# --- КАСТОМНЫЙ CSS (Стиль ECharts Gallery) ---
st.markdown("""
    <style>
    /* Общие настройки */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }

    /* Стиль сайдбара как в ECharts Gallery */
    [data-testid="stSidebar"] {
        background-color: #0d1117;
        border-right: 1px solid #1e2227;
        padding-top: 1rem;
        padding-bottom: 1rem;
    }

    [data-testid="stSidebar"] .sidebar-content {
        background-color: #0d1117;
    }

    /* Заголовок сайдбара */
    [data-testid="stSidebar"] h1 {
        color: #ffffff;
        font-size: 1.5rem;
        margin-bottom: 0.5rem;
        padding-left: 1rem;
    }

    [data-testid="stSidebar"] .sidebar-content h2 {
        color: #8b949e;
        font-size: 1.1rem;
        font-weight: 600;
        padding: 0.75rem 1rem 0.25rem;
        border-bottom: 1px solid #21262d;
        margin-top: 1.5rem;
    }

    [data-testid="stSidebar"] .sidebar-content h3 {
        color: #8b949e;
        font-size: 1rem;
        font-weight: 500;
        padding: 0.5rem 1rem;
        margin: 0;
    }

    /* Кнопки навигации */
    [data-testid="stSidebar"] .stButton>button {
        width: 100%;
        background-color: #161b22;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin: 0.25rem 1rem;
        transition: 0.3s;
        text-align: left;
    }

    [data-testid="stSidebar"] .stButton>button:hover {
        background-color: #1f262d;
        border-color: #3f51b5;
        color: #ffffff;
    }

    [data-testid="stSidebar"] .stButton>button:active {
        background-color: #21262d;
        border-color: #3f51b5;
    }

    [data-testid="stSidebar"] .stButton>button.selected {
        background-color: #1f262d;
        border-color: #3f51b5;
        color: #ffffff;
        font-weight: 600;
    }

    /* Ссылки в сайдбаре */
    [data-testid="stSidebar"] a {
        color: #8b949e;
        text-decoration: none;
        padding: 0.5rem 1rem;
        display: block;
        margin: 0.25rem 1rem;
        border-radius: 6px;
    }

    [data-testid="stSidebar"] a:hover {
        color: #ffffff;
        background-color: #1f262d;
    }

    /* Кнопка поддержки */
    [data-testid="stSidebar"] .stButton button[data-testid="baseButton-secondary"] {
        background-color: #161b22;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin: 0.5rem 1rem;
        width: 90%;
        text-align: center;
    }

    [data-testid="stSidebar"] .stButton button[data-testid="baseButton-secondary"]:hover {
        background-color: #1f262d;
        color: #ffffff;
    }

    /* Основная область */
    .main {
        background-color: #ffffff;
        color: #24292f;
    }

    .main h1 {
        color: #24292f;
        font-size: 2.2rem;
        margin-bottom: 1rem;
        font-weight: 600;
    }

    .main h2 {
        color: #24292f;
        font-size: 1.5rem;
        margin: 1.5rem 0 1rem;
        font-weight: 600;
    }

    .main h3 {
        color: #24292f;
        font-size: 1.2rem;
        margin: 1rem 0 0.5rem;
        font-weight: 600;
    }

    .main p {
        color: #57606a;
        line-height: 1.5;
    }

    /* Карточки метрик */
    .metric-card {
        background: #f6f8fa;
        border-radius: 10px;
        padding: 1.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s;
    }

    .metric-card:hover {
        transform: translateY(-3px);
    }

    .metric-value {
        font-size: 1.8rem;
        font-weight: 600;
        color: #24292f;
        margin: 0.5rem 0;
    }

    .metric-label {
        color: #57606a;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }

    .metric-change {
        display: inline-block;
        font-size: 0.85rem;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        background: #f0f6fc;
        color: #2a9d8f;
    }

    /* Стили для главной страницы */
    .search-section {
        background: #f6f8fa;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        border: 1px solid #eaecef;
    }

    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #24292f;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .section-title i {
        color: #3f51b5;
    }

    /* Кнопки на главной */
    .main .stButton>button {
        background-color: #24292f;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 0.75rem 1.5rem;
        font-weight: 500;
        transition: 0.3s;
    }

    .main .stButton>button:hover {
        background-color: #1f262d;
    }

    /* Таблицы */
    [data-testid="stDataFrame"] {
        background: #ffffff;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    [data-testid="stDataFrame"] th {
        background: #f6f8fa;
        color: #24292f;
        font-weight: 600;
        padding: 0.75rem 1rem;
    }

    [data-testid="stDataFrame"] td {
        padding: 0.75rem 1rem;
        border-top: 1px solid #eaecef;
    }

    [data-testid="stDataFrame"] tr:hover {
        background-color: #f8f9fa;
    }

    /* Результаты анализа */
    .result-box {
        background: #ffffff; 
        padding: 1.5rem; 
        border-radius: 12px; 
        border-left: 4px solid #3f51b5;
        line-height: 1.6;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    /* Категории и товары */
    .category-expander {
        background: #f6f8fa !important;
        border-radius: 10px !important;
        border: 1px solid #eaecef !important;
        margin-bottom: 1rem !important;
    }

    .category-header {
        font-weight: 600 !important;
        color: #24292f !important;
        padding: 0.75rem 1rem !important;
        background: #f0f6fc !important;
        border-radius: 8px 8px 0 0 !important;
    }

    .category-items {
        padding: 1rem !important;
        background: #ffffff !important;
        border-radius: 0 0 8px 8px !important;
        border-top: 1px solid #eaecef !important;
    }

    .category-item {
        padding: 0.75rem 1rem !important;
        border-radius: 6px !important;
        margin: 0.5rem 0 !important;
        cursor: pointer !important;
        transition: all 0.2s !important;
        border: 1px solid #eaecef !important;
    }

    .category-item:hover {
        background: #f0f6fc !important;
        border-color: #3f51b5 !important;
    }

    .category-item-selected {
        background: #eef2ff !important;
        border-color: #3f51b5 !important;
        color: #24292f !important;
        font-weight: 600;
    }

    .category-search {
        margin: 1rem 0 !important;
    }

    .category-search input {
        background: #ffffff !important;
        border: 1px solid #eaecef !important;
        border-radius: 6px !important;
        color: #24292f !important;
        padding: 0.75rem 1rem !important;
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)


# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    if val == 2 or val == 'Positive': return 'color: #2a9d8f; font-weight: bold;'
    if val == 1 or val == 'Negative': return 'color: #e76f51; font-weight: bold;'
    return 'color: #57606a;'


# --- ПОДГОТОВКА ДАННЫХ ---
product_df = get_all_products()
display_df = product_df.rename(columns={
    'nm_id': 'ID Товара',
    'product_name': 'Наименование',
    'category': 'Категория',
    'sentiment_score': 'Тональность'
})

# --- БОКОВАЯ ПАНЕЛЬ (SIDEBAR) ---
with st.sidebar:
    # Заголовок сайдбара как в ECharts Gallery
    st.markdown("<h1 style='color: #ffffff; margin-bottom: 0.5rem;'>📂 InsightCopy AI</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color: #8b949e; font-size: 0.9rem; margin-top: 0; padding-left: 1rem;'>Sentiment Analysis Dashboard</p>",
        unsafe_allow_html=True)
    st.divider()

    # Навигация как в примере
    st.markdown(
        "<h2 style='color: #8b949e; font-weight: 600; padding: 0.75rem 1rem 0.25rem; border-bottom: 1px solid #21262d; margin-top: 1rem;'>Навигация</h2>",
        unsafe_allow_html=True)

    # Кнопки навигации с подсветкой текущей страницы
    if st.button("🏠 Главная", use_container_width=True,
                 type="primary" if st.session_state.page == "Главная" else "secondary"):
        st.session_state.page = "Главная"
    if st.button("📈 Аналитика", use_container_width=True,
                 type="primary" if st.session_state.page == "Аналитика" else "secondary"):
        st.session_state.page = "Аналитика"
    if st.button("ℹ️ О проекте", use_container_width=True,
                 type="primary" if st.session_state.page == "О проекте" else "secondary"):
        st.session_state.page = "О проекте"

    st.divider()

    # Фильтры как в примере
    st.markdown(
        "<h2 style='color: #8b949e; font-weight: 600; padding: 0.75rem 1rem 0.25rem; border-bottom: 1px solid #21262d; margin-top: 1rem;'>Фильтры</h2>",
        unsafe_allow_html=True)

    # reporting_period = st.selectbox("Reporting Period", ["12 Months", "6 Months", "3 Months"])
    # market = st.selectbox("Market", ["Choose options", "North America", "Europe", "Asia"])
    # category = st.selectbox("Category", ["Choose options", "Electronics", "Apparel", "Home"])
    # sub_category = st.selectbox("Sub-Category", ["Choose options", "Computers", "Phones", "Tablets"])
    # customer_segment = st.selectbox("Customer Segment", ["All", "Consumer", "Corporate"])

    # Добавим фильтры, соответствующие вашему приложению
    st.markdown("<h3 style='color: #8b949e; font-weight: 500; padding: 0.5rem 1rem;'>Период анализа</h3>",
                unsafe_allow_html=True)
    reporting_period = st.selectbox("", ["12 месяцев", "6 месяцев", "3 месяца"], label_visibility="collapsed")

    st.markdown("<h3 style='color: #8b949e; font-weight: 500; padding: 0.5rem 1rem;'>Рынок</h3>",
                unsafe_allow_html=True)
    market = st.selectbox("", ["Выбрать", "Северная Америка", "Европа", "Азия"], label_visibility="collapsed")

    st.markdown("<h3 style='color: #8b949e; font-weight: 500; padding: 0.5rem 1rem;'>Сегмент клиентов</h3>",
                unsafe_allow_html=True)
    customer_segment = st.selectbox("", ["Все", "Потребитель", "Корпоративный"], label_visibility="collapsed")

    st.divider()

    # Ссылка на проект
    st.markdown(
        "<h2 style='color: #8b949e; font-weight: 600; padding: 0.75rem 1rem 0.25rem; border-bottom: 1px solid #21262d; margin-top: 1rem;'>О проекте</h2>",
        unsafe_allow_html=True)
    st.markdown(
        "<p style='color: #8b949e; font-size: 0.9rem; padding: 0.5rem 1rem;'>Система для анализа отзывов и получения инсайтов</p>",
        unsafe_allow_html=True)
    st.markdown("<p style='color: #8b949e; font-size: 0.9rem; padding: 0.5rem 1rem;'>Создано с ❤️ для маркетологов</p>",
                unsafe_allow_html=True)

    st.markdown("<h3 style='color: #8b949e; font-weight: 500; padding: 0.5rem 1rem;'>Репозиторий</h3>",
                unsafe_allow_html=True)
    st.markdown(
        "<p style='color: #8b949e; font-size: 0.9rem; padding: 0.5rem 1rem;'>[GitHub](https://github.com/andfanilo/streamlit-echarts-demo)</p>",
        unsafe_allow_html=True)

    # Кнопка поддержки
    st.button("Buy me a coffee", type="secondary", use_container_width=True)

# --- СТРАНИЦА: ГЛАВНАЯ ---
if st.session_state.page == "Главная":
    st.title("Мониторинг каталога")
    st.markdown(
        "<p style='color: #57606a; font-size: 1.1rem;'>Общая сводка по доступным товарам и их текущему состоянию</p>",
        unsafe_allow_html=True)

    # Метрики в стиле ECharts Gallery
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Товаров в базе</div>
            <div class="metric-value">3</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Активность системы</div>
            <div class="metric-value">Высокая</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Точность BERT</div>
            <div class="metric-value">94%</div>
            <div class="metric-change">↑ 2%</div>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Обработано отзывов</div>
            <div class="metric-value">12,458</div>
            <div class="metric-change">↑ 15.8%</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # --- НОВАЯ СЕКЦИЯ: БАЗА ТОВАРОВ НА ГЛАВНОЙ СТРАНИЦЕ ---
    st.markdown('<div class="search-section">', unsafe_allow_html=True)

    # Заголовок секции
    st.markdown('<div class="section-title"><i>📦</i> База товаров для анализа</div>',
                unsafe_allow_html=True)

    # Поиск по категориям
    search_query = st.text_input(
        "Поиск по категориям",
        placeholder="Например: Электроника",
        label_visibility="collapsed"
    )

    # Группируем товары по категориям
    categories = product_df['category'].unique()

    # Фильтруем категории по запросу
    if search_query:
        filtered_categories = [cat for cat in categories if search_query.lower() in cat.lower()]
    else:
        filtered_categories = categories

    # Если нет результатов поиска
    if len(filtered_categories) == 0 and search_query:
        st.info("Категории не найдены")

    # Создаем раскрывающиеся списки для категорий
    for category in filtered_categories:
        # Используем expander для категории
        with st.expander(f"📦 {category}", expanded=False):
            # Получаем товары в категории
            category_products = product_df[product_df['category'] == category]

            # Показываем количество товаров
            st.markdown(f"<div class='category-header'>{len(category_products)} товаров</div>",
                        unsafe_allow_html=True)

            # Создаем кнопки для каждого товара
            for idx, row in category_products.iterrows():
                # Создаем уникальный ключ для каждой кнопки
                btn_key = f"prod_{row['nm_id']}"

                # Проверяем, выбран ли текущий товар
                is_selected = st.session_state.get('current_sku') == row['nm_id']

                # Стилизуем кнопку в зависимости от состояния
                btn_style = "category-item-selected" if is_selected else "category-item"

                # Создаем кнопку товара
                if st.button(
                        f"▫️ {row['product_name']} ({row['nm_id']})",
                        key=btn_key,
                        use_container_width=True,
                        type="secondary" if not is_selected else "primary"
                ):
                    st.session_state.current_sku = row['nm_id']
                    st.session_state.current_category = category
                    st.toast(f"Товар {row['product_name']} выбран!", icon="✅")

            # Кнопка для анализа всей категории
            if st.button(
                    f"🔍 Проанализировать всю категорию",
                    key=f"cat_analyze_{category}",
                    use_container_width=True,
                    type="secondary"
            ):
                st.session_state.current_category = category
                st.session_state.current_sku = None  # Сбрасываем выбор товара
                st.toast(f"Категория {category} выбрана для анализа!", icon="✅")

    # Кнопка запуска анализа
    if st.button("Запустить анализ", use_container_width=True, type="primary", key="main_analyze"):
        if st.session_state.get('current_sku') or st.session_state.get('current_category'):
            st.toast("Анализ запущен!", icon="🚀")
            st.session_state.page = "Аналитика"  # Автоматический переход на аналитику
        else:
            st.warning("Выберите товар или категорию для анализа")

    st.markdown('</div>', unsafe_allow_html=True)

    # --- НОВАЯ СЕКЦИЯ: СВОИ ДАННЫЕ НА ГЛАВНОЙ СТРАНИЦЕ ---
    st.markdown('<div class="search-section">', unsafe_allow_html=True)

    # Заголовок секции
    st.markdown('<div class="section-title"><i>📁</i> Добавьте свои данные</div>',
                unsafe_allow_html=True)

    # Загрузка файлов
    uploaded_file = st.file_uploader(
        "Загрузите .csv или .xlsx файл с отзывами",
        type=['csv', 'xlsx'],
        label_visibility="collapsed"
    )

    if uploaded_file is not None:
        st.success("Файл успешно загружен!")
        st.caption(f"Размер файла: {round(uploaded_file.size / 1024, 2)} KB")

        # Здесь будет логика обработки файла
        # st.write("Обработка данных...")

        if st.button("Анализировать загруженные данные", use_container_width=True, type="primary"):
            st.toast("Анализ загруженных данных запущен!", icon="🚀")
            st.session_state.page = "Аналитика"  # Автоматический переход на аналитику

    st.markdown('</div>', unsafe_allow_html=True)

    st.divider()

    # Чистая таблица с товарами
    st.subheader("📦 База артикулов")
    if not display_df.empty:
        # Применяем цветовой маппинг к колонке Тональность, если она есть
        target_col = ['Тональность'] if 'Тональность' in display_df.columns else []
        styled_df = display_df.style.map(color_sentiment, subset=target_col)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
    else:
        st.info("В базе данных пока нет информации.")

# --- СТРАНИЦА: АНАЛИТИКА ---
elif st.session_state.page == "Аналитика":
    st.title("Результаты анализа")

    # Проверяем, что выбрана категория или товар
    if st.session_state.get('current_sku'):
        # Анализ для конкретного товара
        current_sku = st.session_state.current_sku
        summary = get_summary(current_sku)

        if summary:
            st.markdown(f"#### 📊 Отчет по товару: {current_sku}")

            # Блок с резюме от нейросети
            st.markdown(f'<div class="result-box">{summary}</div>', unsafe_allow_html=True)

            st.write("")
            # Дополнительные детали
            with st.expander("🔍 Посмотреть исходные данные (отзывы)"):
                reviews = get_reviews(current_sku)
                if reviews is not None and not reviews.empty:
                    st.dataframe(reviews, use_container_width=True)
                else:
                    st.write("Тексты отзывов для этого артикула не найдены.")
        else:
            st.warning(f"Аналитика для артикула {current_sku} еще не сформирована.")

    elif st.session_state.get('current_category'):
        # Анализ для всей категории
        category = st.session_state.current_category
        st.markdown(f"#### 📊 Анализ категории: {category}")

        # Пример результата для категории
        st.markdown("""
        <div class="result-box">
        <b>Основные инсайты по категории "Электроника":</b><br>
        • 78% положительных отзывов<br>
        • Основные преимущества: "отличная камера", "быстрая зарядка"<br>
        • Основные недостатки: "низкое качество звука", "перегрев"<br>
        • Рекомендация: улучшить аудиосистему в следующих моделях
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        st.subheader("Товары в категории")
        category_products = product_df[product_df['category'] == category]
        if not category_products.empty:
            category_display = category_products[['nm_id', 'product_name']].rename(
                columns={'nm_id': 'ID Товара', 'product_name': 'Наименование'}
            )
            st.dataframe(category_display, use_container_width=True)
        else:
            st.info("В этой категории нет товаров")

    else:
        # Состояние "ничего не выбрано"
        st.info("⬅️ Пожалуйста, выберите товар или категорию на главной странице, чтобы увидеть отчет.")

# --- СТРАНИЦА: О ПРОЕКТЕ ---
elif st.session_state.page == "О проекте":
    st.title("О проекте")
    st.markdown("""
    Система InsightCopy AI разработана для автоматизации глубокого анализа клиентского опыта. 
    Мы помогаем селлерам понимать, что именно ценят покупатели и над какими недостатками стоит работать.

    **Ключевой функционал:**
    1.  **Сбор данных**: Автоматизированный парсинг отзывов.
    2.  **Анализ тональности**: Модель **BERT** для точного разделения мнений.
    3.  **Интерпретация**: Выделение смысловых триггеров с помощью **SHAP**.
    4.  **Сводка**: Генерация итогового текста для карточки товара или отдела качества.

    **Технологии:** Python, Streamlit, Yandex Managed PostgreSQL, Transformers.
    """)
    st.divider()
    st.image("https://huggingface.co/front/assets/huggingface_logo-noborder.svg", width=80)