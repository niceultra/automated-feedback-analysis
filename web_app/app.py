import streamlit as st
import pandas as pd
import psycopg2
from PIL import Image

# 1. Настройка страницы в стиле минимализма
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


# --- КАСТОМНЫЙ CSS (Адаптивная тема) ---
st.markdown("""
    <style>
    /* Общие настройки шрифтов и отступов */
    .block-container { padding-top: 2rem; }

    /* Исправленный CSS для сайдбара */
[data-testid="stSidebar"] {
    background-color: #0d1117 !important;  /* Более темный цвет, как в примере */
    border-right: 1px solid #21262d !important;  /* Более контрастная граница */
    padding-top: 1.5rem !important;
    padding-bottom: 1.5rem !important;
}

/* Улучшение структуры сайдбара */
[data-testid="stSidebar"] .sidebar-content {
    background-color: #0d1117 !important;
}

/* Заголовок сайдбара */
[data-testid="stSidebar"] h1 {
    color: #ffffff !important;
    font-size: 1.5rem !important;
    margin-bottom: 0.5rem !important;
    padding-left: 1.5rem !important;
}

/* Разделители в сайдбаре */
[data-testid="stSidebar"] hr {
    border-top: 1px solid #21262d !important;
    margin: 1rem 0 !important;
}

/* Кнопки навигации в сайдбаре */
[data-testid="stSidebar"] .stButton>button {
    width: 100% !important;
    background-color: #161b22 !important;
    color: #c9d1d9 !important;
    border: 1px solid #30363d !important;
    border-radius: 6px !important;
    padding: 0.75rem 1.5rem !important;
    margin: 0.25rem 1.5rem !important;
    transition: 0.3s !important;
    text-align: left !important;
}

/* Активная кнопка навигации */
[data-testid="stSidebar"] .stButton>button[data-testid="baseButton-primary"] {
    background-color: #1f262d !important;
    border-color: #3f51b5 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}

/* Поддержка разных тем */
[data-theme="light"] [data-testid="stSidebar"] {
    background-color: #f8f9fa !important;
    border-right: 1px solid #eaecef !important;
}

[data-theme="light"] [data-testid="stSidebar"] .stButton>button {
    background-color: #ffffff !important;
    color: #24292f !important;
    border: 1px solid #eaecef !important;
}

[data-theme="light"] [data-testid="stSidebar"] .stButton>button[data-testid="baseButton-primary"] {
    background-color: #f0f6fc !important;
    border-color: #3f51b5 !important;
    color: #24292f !important;
}
    /* Адаптивные стили для основного контента */
    .main {
        background-color: var(--background-color);
        color: var(--text-color);
    }

    /* Кнопки: адаптивные стили */
    .stButton>button {
        width: 100%;
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem;
        transition: 0.3s;
    }
    .stButton>button:hover {
        border-color: var(--primary-color) !important;
        background-color: var(--tertiary-background-color) !important;
    }

    /* Зона загрузки файлов */
    [data-testid="stFileUploadDropzone"] {
        border: 1px dashed var(--border-color) !important;
        background: var(--background-color);
        border-radius: 10px;
    }

    /* Таблица: адаптивные стили */
    [data-testid="stDataFrame"] {
        border: none !important;
        background-color: var(--background-color);
        color: var(--text-color);
    }

    [data-testid="stDataFrame"] th {
        background-color: var(--secondary-background-color);
        color: var(--text-color);
        font-weight: 600;
    }

    [data-testid="stDataFrame"] td {
        border-top: 1px solid var(--border-color);
    }

    /* Стилизация текста результатов */
    .result-box {
        background: var(--secondary-background-color); 
        padding: 25px; 
        border-radius: 15px; 
        border-left: 5px solid var(--primary-color);
        line-height: 1.6;
        color: var(--text-color);
    }

    /* Скрытие стандартных радио-кнопок для чистоты */
    .stRadio [data-testid="stWidgetLabel"] { display: none; }

    /* Адаптивные стили для категорий */
    .category-expander {
        background: var(--secondary-background-color) !important;
        border-radius: 10px !important;
        border: 1px solid var(--border-color) !important;
        margin-bottom: 10px !important;
    }
    .category-header {
        font-weight: 600 !important;
        color: var(--text-color) !important;
        padding: 10px !important;
    }
    .category-items {
        padding: 10px !important;
        background: var(--background-color) !important;
        border-radius: 8px !important;
    }
    .category-item {
        padding: 8px 12px !important;
        border-radius: 6px !important;
        margin: 5px 0 !important;
        cursor: pointer !important;
        transition: all 0.2s !important;
        border: 1px solid var(--border-color) !important;
    }
    .category-item:hover {
        background: var(--tertiary-background-color) !important;
        border-color: var(--primary-color) !important;
    }
    .category-item-selected {
        background: var(--primary-color) !important;
        border-color: var(--primary-color) !important;
        color: white !important;
    }
    .category-search {
        margin-top: 15px !important;
    }
    .category-search input {
        background: var(--background-color) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        color: var(--text-color) !important;
        padding: 8px 12px !important;
    }

    /* Стили для метрик */
    .metric-card {
        background: var(--secondary-background-color);
        border-radius: 10px;
        padding: 1.5rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .metric-value {
        font-size: 1.8rem;
        font-weight: 600;
        color: var(--text-color);
        margin: 0.5rem 0;
    }

    .metric-label {
        color: var(--text-color-secondary);
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }

    .metric-change {
        display: inline-block;
        font-size: 0.85rem;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        background: var(--tertiary-background-color);
        color: var(--text-color-secondary);
    }

    /* Стили для главной страницы */
    .search-section {
        background: var(--secondary-background-color);
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 25px;
        border: 1px solid var(--border-color);
    }
    .section-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: var(--text-color);
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-title i {
        color: var(--primary-color);
    }

    /* Адаптивные стили для заголовков */
    h1, h2, h3, h4 {
        color: var(--text-color) !important;
    }

    p {
        color: var(--text-color-secondary) !important;
    }

    /* Адаптивные стили для отчетов */
    .report-section {
        background: var(--secondary-background-color);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid var(--border-color);
    }

    .report-title {
        color: var(--text-color);
        font-size: 1.3rem;
        font-weight: 600;
        margin-bottom: 15px;
    }

    .report-content {
        color: var(--text-color);
        line-height: 1.6;
    }
    </style>
    """, unsafe_allow_html=True)


# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    if val == 2 or val == 'Positive':
        return 'color: var(--positive-color); font-weight: bold;'
    if val == 1 or val == 'Negative':
        return 'color: var(--negative-color); font-weight: bold;'
    return 'color: var(--text-color-secondary);'


# Добавим кастомные переменные для тональности
st.markdown("""
<style>
    :root {
        --positive-color: #4CAF50;
        --negative-color: #F44336;
    }
    [data-theme="light"] {
        --positive-color: #2E7D32;
        --negative-color: #C62828;
    }
</style>
""", unsafe_allow_html=True)

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
    st.title("📂 InsightCopy AI")
    st.caption("Sentiment Analysis Dashboard")
    st.divider()

    # Навигация через кнопки (без выпадающего списка)
    st.markdown("### Навигация")
    if st.button("🏠 Главная", use_container_width=True):
        st.session_state.page = "Главная"
    if st.button("📈 Аналитика", use_container_width=True):
        st.session_state.page = "Аналитика"
    if st.button("ℹ️ О проекте", use_container_width=True):
        st.session_state.page = "О проекте"

    st.divider()

# --- СТРАНИЦА: ГЛАВНАЯ ---
if st.session_state.page == "Главная":
    st.title("Мониторинг каталога")
    st.markdown("<p style='opacity: 0.6;'>Общая сводка по доступным товарам и их текущему состоянию</p>",
                unsafe_allow_html=True)

    # Метрики без рамок для чистоты
    m1, m2, m3 = st.columns(3)
    m1.metric("Товаров в базе", len(product_df))
    m2.metric("Активность системы", "Высокая")
    m3.metric("Точность BERT", "94%", delta="↑ 2%")

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