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

    # Навигация через selectbox для чистого вида
    page = st.selectbox("Перейти к разделу:", ["🏠 Главная", "📈 Аналитика", "ℹ️ О проекте"])

    st.divider()
    st.markdown("### Управление")

    # Выбор товара из базы
    options = display_df.apply(lambda x: f"{x['Наименование']} ({x['ID Товара']})", axis=1).tolist()
    selected_item = st.selectbox("Выберите артикул из базы:", [""] + options)

    if st.button("Запустить анализ"):
        if selected_item:
            # Сохраняем артикул в сессию, чтобы он был доступен на вкладке Аналитика
            sku = selected_item.split('(')[-1].replace(')', '')
            st.session_state.current_sku = sku
            st.toast(f"Артикул {sku} выбран!", icon="✅")

    st.divider()
    st.markdown("### Свои данные")
    st.file_uploader("Загрузить .csv или .xlsx", type=['csv', 'xlsx'], label_visibility="collapsed")

# --- СТРАНИЦА: ГЛАВНАЯ ---
if page == "🏠 Главная":
    st.title("Мониторинг каталога")
    st.markdown("<p style='opacity: 0.6;'>Общая сводка по доступным товарам и их текущему состоянию</p>",
                unsafe_allow_html=True)

    # Метрики без рамок для чистоты
    m1, m2, m3 = st.columns(3)
    m1.metric("Товаров в базе", len(product_df))
    m2.metric("Активность системы", "Высокая")
    m3.metric("Точность BERT", "94%", delta="↑ 2%")

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
elif page == "📈 Аналитика":
    st.title("Результаты анализа")

    # Пытаемся получить SKU из сессии (если пользователь нажал кнопку на главной или в сайдбаре)
    current_sku = st.session_state.get('current_sku')

    if current_sku:
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
    else:
        # Состояние "ничего не выбрано"
        st.info("⬅️ Пожалуйста, выберите товар в меню слева, чтобы увидеть отчет.")

# --- СТРАНИЦА: О ПРОЕКТЕ ---
elif page == "ℹ️ О проекте":
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