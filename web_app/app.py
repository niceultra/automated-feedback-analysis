import os
import streamlit as st
import pandas as pd
import psycopg2
import streamlit.components.v1 as components
from PIL import Image
import plotly.express as px
import requests
import uuid
import base64
import time
from requests.exceptions import SSLError


def local_css(file_name):
    # Получаем абсолютный путь к директории, где лежит сам скрипт
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    # Соединяем путь с именем файла
    file_path = os.path.join(parent_dir, file_name)

    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        st.error(f"Файл {file_name} не найден по пути: {file_path}")

local_css("style.css")


# 1. Открываем изображение с помощью PIL
img = Image.open("./images/logo.png")
# 2. Передаем объект изображения в конфигурацию
st.set_page_config(
    page_title="ИнСайт Бот • Умная аналитика отзывов",
    page_icon=img,
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


def generate_marketing_content(strengths, weaknesses):
    """
    Генерирует маркетинговый отчет с использованием GigaChat API
    """
    # Проверка наличия необходимых секретов
    required_secrets = ["GIGACHAT_CLIENT_ID", "GIGACHAT_CLIENT_SECRET"]
    missing_secrets = [s for s in required_secrets if s not in st.secrets]

    if missing_secrets:
        return f"Ошибка: Не найдены секреты в приложении: {', '.join(missing_secrets)}\n\nДобавьте их в .streamlit/secrets.toml"

    client_id = st.secrets["GIGACHAT_CLIENT_ID"]
    client_secret = st.secrets["GIGACHAT_CLIENT_SECRET"]

    auth_string = f"{client_id}:{client_secret}"

    # Правильное Base64 кодирование (убираем b' и trailing = если нужно)
    import base64
    auth_bytes = auth_string.encode('utf-8')
    base64_bytes = base64.b64encode(auth_bytes)
    base64_string = base64_bytes.decode('utf-8')

    # Шаг 1: Получаем Access Token
    token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    scope = "GIGACHAT_API_PERS"
    rq_uid = str(uuid.uuid4())

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': rq_uid,
        'Authorization': f'Basic {base64_string}'
    }

    payload = {
        'scope': scope
    }

    try:
        # Отключаем проверку SSL (временно для тестирования)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.post(
            token_url,
            headers=headers,
            data=payload,
            verify=False,
            timeout=10
        )


        if response.status_code != 200:
            return f"Ошибка при получении токена ({response.status_code}): {response.text}"

        access_token = response.json().get('access_token')
        if not access_token:
            return f"Не удалось получить access_token: {response.text}"

        # Шаг 2: Готовим промпт
        prompt = f"""
        Ты — ведущий маркетинговый аналитик. На основе данных анализа отзывов составь стратегический отчет для продавца на маркетплейсе.

        СИЛЬНЫЕ СТОРОНЫ ТОВАРА:
        {', '.join(strengths) if strengths else 'Не выявлено'}

        СЛАБЫЕ СТОРОНЫ ТОВАРА:
        {', '.join(weaknesses) if weaknesses else 'Не выявлено'}

        Твоя задача составить отчет по следующим пунктам:
        1. Уникальное торговое предложение (УТП) — на чем сделать акцент в рекламе.
        2. Рекомендации по улучшению продукта — как устранить негатив.
        3. Идеи для инфографики — какие буллиты вынести на главные фото.
        4. Тональность ответов — как общаться с покупателями в отзывах.

        Пиши профессионально, лаконично и на русском языке. Используй Markdown для оформления.
        """

        # Шаг 3: Отправляем запрос к GigaChat
        chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

        chat_payload = {
            "model": "GigaChat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }

        chat_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }

        # Повторяем запрос при ошибках SSL (частая проблема с Сбером)
        for attempt in range(3):
            try:
                chat_response = requests.post(
                    chat_url,
                    headers=chat_headers,
                    json=chat_payload,
                    verify=False,
                    timeout=30
                )
                break
            except SSLError:
                if attempt == 2:
                    raise
                time.sleep(1)

        chat_response.raise_for_status()
        result = chat_response.json()

        # Извлекаем ответ из структуры GigaChat
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            return f"Неожиданный формат ответа от API: {result}"

    except Exception as e:
        return f"Произошла ошибка при работе с GigaChat API: {str(e)}"

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


def get_product_summary(nm_id):
    """
    Получает полную аналитику товара из базы данных

    Args:
        nm_id (str): Артикул товара

    Returns:
        dict: Словарь с данными аналитики
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Выбираем необходимые колонки
        query = """
        SELECT 
            summary_text,
            chart_html
        FROM 
            product_summary
        WHERE 
            nm_id = %s
        """
        cursor.execute(query, (str(nm_id),))
        result = cursor.fetchone()

        conn.close()

        if result:
            return {
                'summary_text': result[0],
                'chart_html': result[1]
            }
        else:
            return None
    except Exception as e:
        st.error(f"Ошибка при получении аналитики: {str(e)}")
        return None


def extract_strengths_weaknesses(summary_text):
    """
    Извлекает сильные и слабые стороны из текста аналитики

    Args:
        summary_text (str): Текст аналитики из БД

    Returns:
        tuple: (список сильных сторон, список слабых сторон)
    """
    if not summary_text:
        return [], []

    strengths = []
    weaknesses = []

    try:
        # Ищем раздел с ключевыми плюсами и минусами
        strengths_start = summary_text.find("КЛЮЧЕВЫЕ ПЛЮСЫ:")
        weaknesses_start = summary_text.find("КЛЮЧЕВЫЕ МИНУСЫ:")

        if strengths_start != -1 and weaknesses_start != -1:
            # Извлекаем текст между разделами
            strengths_text = summary_text[strengths_start + len("КЛЮЧЕВЫЕ ПЛЮСЫ:"):weaknesses_start].strip()
            weaknesses_text = summary_text[weaknesses_start + len("КЛЮЧЕВЫЕ МИНУСЫ:"):].strip()

            # Функция для парсинга пунктов
            def parse_points(text):
                points = []
                for line in text.split('\n'):
                    line = line.strip()
                    # Ищем строки, которые начинаются с цифры и точки/скобки
                    if line and len(line) > 2 and line[0].isdigit() and (line[1] == '.' or line[1] == ')'):
                        # Удаляем номер пункта
                        point = line[2:].strip().rstrip('.')
                        if point:
                            points.append(point)
                return points

            # Парсим сильные стороны
            strengths = parse_points(strengths_text)

            # Парсим слабые стороны
            weaknesses = parse_points(weaknesses_text)
    except Exception as e:
        st.error(f"Ошибка при извлечении данных: {str(e)}")

    return strengths, weaknesses
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
    # --- ЗАГОЛОВОК С ВАШЕЙ КАРТИНКОЙ ---
    # Создаем две колонки: узкую для лого и широкую для текста
    col1, col2 = st.columns([1, 4])

    with col1:
        # Укажите путь к вашему логотипу. Ширину (width) подберите под себя
        st.image("./images/logo.png", width=45)

    with col2:
        # Текст заголовка без эмодзи
        st.markdown(
            """
            <h1 style='margin-top: 10px; margin-bottom: 0; padding: 0;'>
                ИнСайт<span style='color: #28a745;'> Бот</span>
            </h1>
            """,
            unsafe_allow_html=True
        )

    st.caption("Умная аналитика отзывов")
    st.divider()

    if st.button("Главная", icon=":material/home:", use_container_width=True):
        st.session_state.page = "Главная"

    if st.button("Аналитика", icon=":material/monitoring:", use_container_width=True):
        st.session_state.page = "Аналитика"

    if st.button("О проекте", icon=":material/info:", use_container_width=True):
        st.session_state.page = "О проекте"

# --- СТРАНИЦА: ГЛАВНАЯ ---
if st.session_state.page == "Главная":
    st.title("Аналитика отзывов с маркетплейсов")
    st.markdown("<p style='color: #28a745; font-style: italic;margin-bottom: 25px;'>Автосбор и AI-анализ инсайтов</p>", unsafe_allow_html=True)

    # Метрики (оставляем как есть)
    m1, m2, m3 = st.columns(3)
    m1.metric("Позиций в базе", f'{len(product_df)}')
    m2.metric("Активность системы", "Высокая")
    m3.metric("Точность модели", "94%", delta="↑ 2%")

    st.divider()

    st.markdown(
        """
        <style>
        .custom-text {
            font-style: italic;
            color: #707070; /* Светло-серый цвет */
            margin-bottom: 20px; /* Отступ снизу */
        }
        </style>
        <div class="custom-text">
            Выберите категорию или артикул товара, чтобы увидеть аналитику
        </div>
        """,
        unsafe_allow_html=True
    )
    # --- СОЗДАЕМ КОЛОНКИ ---
    # ratio [2, 1] значит, что левая колонка будет в два раза шире правой
    col_nav, col_upload = st.columns([2, 1], gap="large")

    # --- ЛЕВАЯ КОЛОНКА: НАВИГАЦИЯ ---
    with col_nav:
        search_query = st.text_input(
            "Поиск по категориям",
            placeholder="Например: Красота",
            label_visibility="collapsed"
        )

        if not product_df.empty:
            categories = product_df['category_name'].unique()
            if search_query:
                categories = [cat for cat in categories if search_query.lower() in cat.lower()]

            for category in categories:
                with st.expander(f"{category}", expanded=False):
                    cat_prods = product_df[product_df['category_name'] == category]
                    for _, row in cat_prods.iterrows():
                        is_active = st.session_state.current_sku == row['nm_id']

                        # Используем нормальную Google-иконку, как обсуждали ранее
                        icon_name = ":material/check_circle:" if is_active else None

                        if st.button(
                                row['product_name'],
                                icon=icon_name,
                                key=f"btn_{row['nm_id']}",
                                use_container_width=True
                        ):
                            st.session_state.current_sku = row['nm_id']
                            st.session_state.current_category = category
                            st.rerun()

            # --- УЛУЧШЕНИЕ: КНОПКА ПЕРЕХОДА К АНАЛИТИКЕ ---
            if st.session_state.current_sku:
                st.write("")  # Отступ
                # Находим имя выбранного товара для красоты
                selected_name = product_df[product_df['nm_id'] == st.session_state.current_sku]['product_name'].values[
                    0]

                st.info(f"Выбран товар: **{selected_name}**")

                # Большая кнопка перехода
                if st.button("Анализировать", type="primary", use_container_width=True):
                    st.session_state.page = "Аналитика"
                    st.rerun()

    # --- ПРАВАЯ КОЛОНКА: ЗАГРУЗКА ФАЙЛОВ ---
    with col_upload:
        st.markdown("### Загрузка данных")
        uploaded_files = st.file_uploader(
            "Перетащите файл с отзывами сюда, чтобы проанализировать с помощью нейросети",
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            help="Поддерживаются форматы CSV и Excel"
        )

        if uploaded_files:
            for uploaded_file in uploaded_files:
                st.success(f"Файл '{uploaded_file.name}' готов к обработке")
                # Здесь будет ваша логика обработки файлов



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

        # Получаем полную аналитику из БД
        product_summary = get_product_summary(current_sku)

        if product_summary and product_summary['summary_text']:
            summary_text = product_summary['summary_text']
            st.markdown(f"#### Отчет по товару: {current_sku}")

            # СОЗДАЕМ ДВЕ КОЛОНКИ: ГРАФИК СЛЕВА, ТЕКСТ СПРАВА
            col_text, col_chart = st.columns([2, 1])

            # --- ЛЕВАЯ КОЛОНКА: КРУГОВАЯ ДИАГРАММА ---
            with col_chart:
                st.markdown('<div style="text-align: center; width: 100%; margin: 0 auto;">Распределение мнений</div>', unsafe_allow_html=True)

                reviews_df = get_reviews(current_sku)

                if reviews_df is not None and not reviews_df.empty:
                    # ПРИНУДИТЕЛЬНОЕ ИСПРАВЛЕНИЕ:
                    # 1. Убираем возможные пустые значения в sentiment
                    reviews_df = reviews_df.dropna(subset=['sentiment'])
                    # 2. Приводим к типу int (чтобы 2.0 или "2" стали просто 2)
                    reviews_df['sentiment'] = reviews_df['sentiment'].astype(int)

                    # Подсчитываем тональность
                    sentiment_counts = reviews_df['sentiment'].value_counts().reset_index()
                    sentiment_counts.columns = ['sentiment', 'count']

                    # Словарь меток
                    sentiment_labels = {0: 'Нейтральные', 1: 'Негативные', 2: 'Позитивные'}

                    # Добавляем текстовую колонку 'label' на основе числового sentiment
                    sentiment_counts['label'] = sentiment_counts['sentiment'].map(sentiment_labels)

                    # Если после map появились NaN (например, если в базе было число 3), удаляем их
                    sentiment_counts = sentiment_counts.dropna(subset=['label'])

                    # Цветовая карта
                    label_colors = {
                        'Нейтральные': '#9e9e9e',
                        'Негативные': '#f44336',
                        'Позитивные': '#4caf50'
                    }

                    # Создаем круговую диаграмму
                    fig = px.pie(
                        sentiment_counts,
                        values='count',
                        names='label',  # Используем текстовую колонку для имен
                        color='label',  # И для цвета
                        color_discrete_map=label_colors,
                        hole=0.4
                    )

                    fig.update_traces(
                        textposition='inside',
                        textinfo='percent+label',
                        hovertemplate="<b>%{label}</b><br>Количество: %{value}<br>Доля: %{percent}<extra></extra>"
                    )

                    fig.update_layout(
                        showlegend=False,
                        margin=dict(t=10, b=10, l=10, r=10),
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        height=300
                    )

                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                    # Кастомная легенда
                    st.markdown(f"""
                    <div style="display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; font-size: 0.8em;">
                        <span style="color: #4caf50;">● Позитив</span>
                        <span style="color: #f44336;">● Негатив</span>
                        <span style="color: #9e9e9e;">● Нейтрально</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.info("Нет данных для анализа")

            # --- ПРАВАЯ КОЛОНКА: ТЕКСТОВОЕ РЕЗЮМЕ ---
            with col_text:
                st.markdown(f'<div class="result-box">{summary_text}</div>', unsafe_allow_html=True)

                # --- ГЕНЕРАЦИЯ МАРКЕТИНГОВОГО КОНТЕНТА ---
                st.markdown('<div class="section-title">💡 Генерация маркетингового контента</div>',
                            unsafe_allow_html=True)

                # Извлекаем сильные и слабые стороны
                strengths, weaknesses = extract_strengths_weaknesses(summary_text)

                # Проверяем, есть ли данные для генерации
                if strengths or weaknesses:
                    # Показываем краткую статистику
                    st.caption(f"Найдено: {len(strengths)} сильных сторон и {len(weaknesses)} слабых сторон")

                    # Кнопка для генерации контента
                    if st.button("Сгенерировать стратегический маркетинговый отчет",
                                 type="primary",
                                 icon=":material/rocket_launch:",
                                 use_container_width=True):
                        with st.spinner("Генерация контента ... Это займет 15-20 секунд"):
                            # Генерируем контент
                            marketing_content = generate_marketing_content(strengths, weaknesses)

                            # Сохраняем результат в состояние
                            st.session_state.marketing_content = marketing_content
                            st.session_state.content_generated = True

                # Отображаем результат, если он уже сгенерирован
                if 'content_generated' in st.session_state and st.session_state.content_generated:
                    st.markdown(st.session_state.marketing_content)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # Добавляем кнопки действий
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        st.download_button(
                            label="Скачать отчет",
                            data=st.session_state.marketing_content,
                            file_name=f"marketing_report_{current_sku}.md",
                            mime="text/markdown",
                            use_container_width=True,
                            icon=":material/download:"
                        )

                    with col2:
                        if st.button("Сгенерировать заново",
                                     use_container_width=True,
                                     icon=":material/refresh:"):
                            # Удаляем предыдущий результат
                            if 'marketing_content' in st.session_state:
                                del st.session_state.marketing_content
                            if 'content_generated' in st.session_state:
                                del st.session_state.content_generated
                            st.rerun()

            # 3. Исходные отзывы
            with st.expander("🔍 Подробная статистика отзывов"):
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