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


# --- КАСТОМНЫЙ CSS (Минимализм и чистые линии) ---
st.markdown("""
    <style>
    /* Общие настройки шрифтов и отступов */
    .block-container { padding-top: 2rem; }

    /* Чистый Sidebar */
    [data-testid="stSidebar"] {
        background-color: #111418;
        border-right: 1px solid #1e2227;
    }

    /* Кнопки: Акцент на стиле, а не на цвете */
    .stButton>button {
        width: 100%;
        background-color: #2e343d !important;
        color: #ffffff;
        border: 1px solid #4a505e !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem;
        transition: 0.3s;
    }
    .stButton>button:hover {
        border-color: #3f51b5 !important;
        background-color: #1e2227 !important;
    }

    /* Зона загрузки файлов */
    [data-testid="stFileUploadDropzone"] {
        border: 1px dashed #4a505e !important;
        background: #0d1117;
        border-radius: 10px;
    }

    /* Таблица: Убираем визуальный шум */
    [data-testid="stDataFrame"] { border: none !important; }

    /* Стилизация текста результатов */
    .result-box {
        background: #1a1c23; 
        padding: 25px; 
        border-radius: 15px; 
        border-left: 5px solid #3f51b5;
        line-height: 1.6;
    }

    /* Скрытие стандартных радио-кнопок для чистоты */
    .stRadio [data-testid="stWidgetLabel"] { display: none; }

    /* Улучшаем мобильную адаптацию для категорий */
    .category-expander {
        background: #1e2227 !important;
        border-radius: 10px !important;
        border: 1px solid #2e343d !important;
        margin-bottom: 10px !important;
    }
    .category-header {
        font-weight: 600 !important;
        color: #a0a0a0 !important;
        padding: 10px !important;
    }
    .category-items {
        padding: 10px !important;
        background: #15181d !important;
        border-radius: 8px !important;
    }
    .category-item {
        padding: 8px 12px !important;
        border-radius: 6px !important;
        margin: 5px 0 !important;
        cursor: pointer !important;
        transition: all 0.2s !important;
        border: 1px solid #2e343d !important;
    }
    .category-item:hover {
        background: #2e343d !important;
        border-color: #3f51b5 !important;
    }
    .category-item-selected {
        background: #3f51b5 !important;
        border-color: #3f51b5 !important;
        color: white !important;
    }
    .category-search {
        margin-top: 15px !important;
    }
    .category-search input {
        background: #1e2227 !important;
        border: 1px solid #2e343d !important;
        border-radius: 8px !important;
        color: white !important;
        padding: 8px 12px !important;
    }

    /* Стили для главной страницы */
    .search-section {
        background: #15181d;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 25px;
        border: 1px solid #2e343d;
    }
    .section-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #a0a0a0;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .section-title i {
        color: #3f51b5;
    }
    </style>
    """, unsafe_allow_html=True)


# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    if val == 2 or val == 'Positive': return 'color: #4caf50; font-weight: bold;'
    if val == 1 or val == 'Negative': return 'color: #f44336; font-weight: bold;'
    return 'color: #9e9e9e;'


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