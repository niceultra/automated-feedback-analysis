import os
import re
import streamlit as st
import pandas as pd
from PIL import Image
import plotly.express as px

from services.marketing_service import (
    extract_strengths_weaknesses,
    parse_summary_stats,
    build_marketing_recommendations,
    build_ad_brief,
    build_marketing_action_blocks,
    marketing_report_to_excel_bytes,
)

from services.gigachat_service import generate_marketing_content_with_gigachat
from services.db_service import (
    get_all_products,
    get_reviews,
    get_product_summary,
    save_uploaded_analysis_to_db,
)
from services.wb_service import (
    parse_wb_products_input,
    fetch_wb_reviews_dataframe,
)
from services.analysis_service import (
    MIN_REVIEWS_FOR_ANALYSIS,
    read_uploaded_reviews_file,
    analyze_uploaded_reviews,
    dataframe_to_excel_bytes,
)

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


def generate_marketing_content(product_name, strengths, weaknesses):
    """Генерирует маркетинговый комплект через GigaChat."""
    client_id = st.secrets.get("GIGACHAT_CLIENT_ID", None)
    client_secret = st.secrets.get("GIGACHAT_CLIENT_SECRET", None)

    verify_ssl = str(
        st.secrets.get("GIGACHAT_VERIFY_SSL", "true")
    ).strip().lower() in ("1", "true", "yes", "y", "да")

    debug = str(
        st.secrets.get("GIGACHAT_DEBUG", "false")
    ).strip().lower() in ("1", "true", "yes", "y", "да")

    return generate_marketing_content_with_gigachat(
        product_name=product_name,
        strengths=strengths,
        weaknesses=weaknesses,
        client_id=client_id,
        client_secret=client_secret,
        verify_ssl=verify_ssl,
        debug=debug,
    )

# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    # Соответствие согласно Ledger: 1-neg, 2-pos, 0-neutral
    if val == 2 or val == 'Positive': return 'color: #4caf50; font-weight: bold;'
    if val == 1 or val == 'Negative': return 'color: #f44336; font-weight: bold;'
    return 'color: #9e9e9e;'


def normalize_sku(value):
    """Приводит артикул к единому строковому виду для сравнения."""
    if value is None:
        return ""
    return str(value).strip()


def get_product_row_by_sku(products_df, sku):
    """Безопасно ищет товар в product_df по артикулу без ошибки IndexError."""
    if products_df is None or products_df.empty or "nm_id" not in products_df.columns:
        return pd.DataFrame()

    sku_str = normalize_sku(sku)
    return products_df[products_df["nm_id"].astype(str).str.strip() == sku_str]


def get_product_name_by_sku(products_df, sku):
    """Возвращает название товара или безопасную заглушку, если товара нет в product_df."""
    product_row = get_product_row_by_sku(products_df, sku)

    if not product_row.empty and "product_name" in product_row.columns:
        value = product_row.iloc[0]["product_name"]
        if pd.notna(value) and str(value).strip() and str(value).strip().lower() != "nan":
            return str(value).strip()

    return f"Товар {normalize_sku(sku)}"

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

    st.caption("Поиск и анализ отзывов WB")
    st.divider()

    if st.button("Поиск и анализ", icon=":material/search:", width="stretch"):
        st.session_state.page = "Главная"

    if st.button("Аналитика", icon=":material/monitoring:", width="stretch"):
        st.session_state.page = "Аналитика"

    if st.button("О проекте", icon=":material/info:", width="stretch"):
        st.session_state.page = "О проекте"

# --- СТРАНИЦА: ГЛАВНАЯ ---
if st.session_state.page == "Главная":
    st.title("AI-анализ отзывов для маркетолога")

    st.markdown(
        """
        <p style='color: #5f6368; font-size: 1.05rem; margin-bottom: 20px;'>
            Введите артикул или ссылку на товар Wildberries. Сервис соберёт отзывы,
            определит тональность, выделит сильные и слабые стороны товара и подготовит
            практические маркетинговые рекомендации.
        </p>
        """,
        unsafe_allow_html=True
    )

    # Короткие понятные метрики без неподтверждённых заявлений о точности
    m1, m2, m3 = st.columns(3)
    m1.metric("Товаров в базе", f"{len(product_df)}")
    m2.metric("Минимум для анализа", f"{MIN_REVIEWS_FOR_ANALYSIS}+ отзывов")
    m3.metric("Форматы данных", "WB + CSV/XLSX")

    st.divider()

    st.markdown("### Быстрый анализ товара")

    st.info(
        "Основной сценарий: вставьте ссылку или артикул товара, запустите анализ "
        "и получите готовые выводы для карточки товара, рекламы и работы с возражениями."
    )

    col_analyze, col_saved = st.columns([1.35, 1], gap="large")

    # --- ЛЕВАЯ КОЛОНКА: ОСНОВНОЙ СЦЕНАРИЙ ---
    with col_analyze:
        st.markdown("#### 1. Введите товар")

        wb_products_text = st.text_area(
            "Артикул или ссылка Wildberries",
            placeholder=(
                "175088486\n"
                "https://www.wildberries.ru/catalog/175088486/detail.aspx"
            ),
            height=120,
            help="Можно указать один или несколько товаров: каждый артикул или ссылку с новой строки."
        )

        with st.expander("Расширенные настройки", expanded=False):
            wb_limit = st.number_input(
                "Лимит отзывов на товар",
                min_value=0,
                max_value=5000,
                value=0,
                step=50,
                help="0 — собрать все найденные отзывы. Если установлен лимит меньше 400, товар может не пройти минимальный порог анализа."
            )

            wb_min_text_length = st.number_input(
                "Минимальная длина текста отзыва",
                min_value=1,
                max_value=500,
                value=20,
                step=1,
                help="Короткие отзывы без содержательного текста будут пропущены."
            )

        st.markdown("#### 2. Запустите анализ")

        if st.button(
                "Проанализировать отзывы",
                type="primary",
                icon=":material/search:",
                width="stretch",
                key="process_wb_search"
        ):
            try:
                products = parse_wb_products_input(wb_products_text)

                with st.spinner("Собираю отзывы, определяю тональность и формирую маркетинговые выводы..."):
                    raw_df, fetch_report = fetch_wb_reviews_dataframe(
                        products,
                        limit=int(wb_limit),
                        min_text_length=int(wb_min_text_length)
                    )

                    st.session_state.wb_fetch_report = fetch_report

                    if raw_df.empty:
                        raise ValueError("Отзывы не найдены или все отзывы были отфильтрованы по длине текста.")

                    analyzed_df, product_summaries = analyze_uploaded_reviews(raw_df)
                    save_uploaded_analysis_to_db(analyzed_df, product_summaries)

                    first_product = product_summaries[0]
                    st.session_state.current_sku = first_product["nm_id"]
                    st.session_state.current_category = first_product["category_name"]
                    st.session_state.upload_result_df = analyzed_df
                    st.session_state.upload_result_filename = "wb_search_result.xlsx"
                    st.session_state.wb_fetch_report = fetch_report

                st.success(
                    f"Готово: обработано {len(analyzed_df)} отзывов "
                    f"по {len(product_summaries)} товар(ам)."
                )

            except Exception as e:
                st.error(str(e))

        if "wb_fetch_report" in st.session_state:
            with st.expander("Что было найдено на Wildberries", expanded=False):
                st.dataframe(
                    pd.DataFrame(st.session_state.wb_fetch_report),
                    width="stretch",
                    hide_index=True
                )

        if "upload_result_df" in st.session_state:
            st.markdown("#### 3. Получите результат")

            col_download, col_open = st.columns(2)

            with col_download:
                st.download_button(
                    label="Скачать обработанный файл",
                    data=dataframe_to_excel_bytes(st.session_state.upload_result_df),
                    file_name="analyzed_reviews.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                    icon=":material/download:"
                )

            with col_open:
                if st.button(
                        "Открыть аналитику",
                        type="primary",
                        width="stretch",
                        icon=":material/monitoring:"
                ):
                    st.session_state.page = "Аналитика"
                    st.rerun()

        with st.expander("У меня уже есть файл с отзывами CSV или Excel", expanded=False):
            st.caption(
                "Этот режим нужен, если отзывы уже собраны парсером или подготовлены вручную. "
                "Желательные колонки: nmId, product_name, category_name, product_url, rating, text."
            )

            uploaded_files = st.file_uploader(
                "Загрузите файл с отзывами",
                type=["csv", "xlsx"],
                accept_multiple_files=True,
                help="Поддерживаются CSV и Excel."
            )

            if uploaded_files:
                for uploaded_file in uploaded_files:
                    st.success(f"Файл '{uploaded_file.name}' загружен")

                    if st.button(
                            f"Проанализировать файл: {uploaded_file.name}",
                            type="primary",
                            icon=":material/database_upload:",
                            width="stretch",
                            key=f"process_upload_{uploaded_file.name}"
                    ):
                        try:
                            with st.spinner("Анализирую отзывы из файла и сохраняю результат..."):
                                raw_df = read_uploaded_reviews_file(uploaded_file)
                                analyzed_df, product_summaries = analyze_uploaded_reviews(raw_df)
                                save_uploaded_analysis_to_db(analyzed_df, product_summaries)

                                first_product = product_summaries[0]
                                st.session_state.current_sku = first_product["nm_id"]
                                st.session_state.current_category = first_product["category_name"]
                                st.session_state.upload_result_df = analyzed_df
                                st.session_state.upload_result_filename = uploaded_file.name

                            st.success(
                                f"Готово: обработано {len(analyzed_df)} отзывов "
                                f"по {len(product_summaries)} товар(ам)."
                            )

                        except Exception as e:
                            st.error(f"Ошибка при обработке файла: {e}")

    # --- ПРАВАЯ КОЛОНКА: ВТОРОСТЕПЕННЫЙ СЦЕНАРИЙ — ПОИСК В БАЗЕ ---
    with col_saved:
        st.markdown("### Найти товар в базе")
        st.caption(
            "Если товар уже анализировали раньше, его можно открыть из сохранённой базы без повторного сбора отзывов."
        )

        base_query = st.text_input(
            "Поиск по базе",
            placeholder="Название, категория или артикул",
            label_visibility="collapsed"
        )

        if not product_df.empty:
            filtered_products = product_df.copy()

            if base_query:
                q = base_query.lower().strip()
                filtered_products = filtered_products[
                    filtered_products['category_name'].fillna('').astype(str).str.lower().str.contains(q, na=False) |
                    filtered_products['product_name'].fillna('').astype(str).str.lower().str.contains(q, na=False) |
                    filtered_products['nm_id'].fillna('').astype(str).str.lower().str.contains(q, na=False)
                ]

            if filtered_products.empty:
                st.info("В базе пока нет товаров по этому запросу. Запустите новый анализ по артикулу или ссылке.")
            else:
                categories = filtered_products['category_name'].fillna('Без категории').unique()

                for category in categories:
                    with st.expander(f"{category}", expanded=False):
                        cat_prods = filtered_products[filtered_products['category_name'].fillna('Без категории') == category]

                        for _, row in cat_prods.iterrows():
                            is_active = normalize_sku(st.session_state.current_sku) == normalize_sku(row['nm_id'])
                            icon_name = ":material/check_circle:" if is_active else None

                            if st.button(
                                    row['product_name'],
                                    icon=icon_name,
                                    key=f"btn_{row['nm_id']}",
                                    width="stretch"
                            ):
                                st.session_state.current_sku = normalize_sku(row['nm_id'])
                                st.session_state.current_category = category
                                st.rerun()

                if st.session_state.current_sku:
                    st.write("")
                    selected_name = get_product_name_by_sku(product_df, st.session_state.current_sku)
                    st.info(f"Выбран товар из базы: **{selected_name}**")

                    if st.button("Открыть сохранённую аналитику", type="primary", width="stretch"):
                        st.session_state.page = "Аналитика"
                        st.rerun()
        else:
            st.info("База пока пустая. Начните с анализа товара по артикулу или ссылке Wildberries.")

    st.divider()

    # Таблица каталога
    st.subheader("База уже проанализированных товаров")
    st.caption("Этот список пополняется автоматически после анализа по артикулу или ссылке или загруженному файлу.")

    if not product_df.empty:
        display_list = product_df[['nm_id', 'product_name', 'category_name']].rename(
            columns={'nm_id': 'Артикул', 'product_name': 'Наименование', 'category_name': 'Категория'}
        )
        st.dataframe(display_list, width="stretch", hide_index=True)
    else:
        st.info("Пока нет сохранённых товаров. Запустите первый анализ через форму выше.")

# --- СТРАНИЦА: АНАЛИТИКА ---
elif st.session_state.page == "Аналитика":
    st.title("Результаты анализа")

    if st.session_state.get('current_sku'):
        current_sku = st.session_state.current_sku

        # Получаем полную аналитику из БД
        product_summary = get_product_summary(current_sku)

        if product_summary and product_summary['summary_text']:
            summary_text = product_summary['summary_text']
            product_name = "Неизвестный товар"
            if not product_df.empty:
                product_name = get_product_name_by_sku(product_df, current_sku)

            st.markdown(f"#### Отчет по товару: {product_name}")


            # СОЗДАЕМ ДВЕ КОЛОНКИ: ГРАФИК СЛЕВА, ТЕКСТ СПРАВА
            col_text, col_chart = st.columns([2, 1])

            # --- ЛЕВАЯ КОЛОНКА: КРУГОВАЯ ДИАГРАММА ---
            with col_chart:
                st.markdown('<div style="text-align: center; width: 100%; margin: 0 auto;">Распределение мнений по тональности</div>', unsafe_allow_html=True)

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

                    st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

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
                st.markdown('<div class="section-title">Генерация маркетингового контента</div>',
                            unsafe_allow_html=True)

                # Извлекаем сильные и слабые стороны
                strengths, weaknesses = extract_strengths_weaknesses(summary_text)

                stats = parse_summary_stats(summary_text)
                recommendations = build_marketing_recommendations(stats, strengths, weaknesses)
                ad_brief = build_ad_brief(product_name, strengths, weaknesses, stats)

                st.markdown("### Маркетинговая интерпретация")

                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Всего отзывов", stats["total"])
                kpi2.metric("Позитив", f'{stats["positive_share"]}%')
                kpi3.metric("Негатив", f'{stats["negative_share"]}%')
                kpi4.metric("Нейтрально", f'{stats["neutral_share"]}%')

                action_blocks = build_marketing_action_blocks(stats, strengths, weaknesses)

                st.markdown("#### Главные выводы по товару")
                for item in action_blocks["main_conclusions"]:
                    st.markdown(f"- {item}")

                tab_card, tab_objections, tab_ads, tab_improvements, tab_brief = st.tabs(
                    [
                        "Карточка товара",
                        "Возражения",
                        "Реклама",
                        "Доработки",
                        "Бриф"
                    ]
                )

                with tab_card:
                    st.markdown("##### Что вынести в карточку товара")
                    for item in action_blocks["card_actions"]:
                        st.markdown(f"- {item}")

                with tab_objections:
                    st.markdown("##### Какие возражения закрыть")
                    for item in action_blocks["objection_actions"]:
                        st.markdown(f"- {item}")

                with tab_ads:
                    st.markdown("##### Что использовать в рекламе")
                    for item in action_blocks["ad_actions"]:
                        st.markdown(f"- {item}")

                with tab_improvements:
                    st.markdown("##### Что требует доработки")
                    for item in action_blocks["improvement_actions"]:
                        st.markdown(f"- {item}")

                with tab_brief:
                    st.markdown("##### Краткий рекламный бриф")
                    st.text(ad_brief)

                with st.expander("Все рекомендации для маркетолога", expanded=False):
                    for rec in recommendations:
                        st.markdown(f"- {rec}")

                st.download_button(
                    label="Скачать Excel-отчёт для маркетолога",
                    data=marketing_report_to_excel_bytes(
                        product_name,
                        current_sku,
                        summary_text,
                        reviews_df,
                        strengths,
                        weaknesses,
                        recommendations
                    ),
                    file_name=f"marketing_report_{current_sku}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                    icon=":material/download:"
                )

                # Проверяем, есть ли данные для генерации
                # Проверяем, есть ли данные для генерации
                if strengths or weaknesses:
                    st.caption(f"Найдено: {len(strengths)} сильных сторон и {len(weaknesses)} слабых сторон")

                    # Основная кнопка генерации
                    if st.button(
                            "Сгенерировать материалы для карточки и рекламы",
                            type="primary",
                            icon=":material/campaign:",
                            width="stretch",
                            key="generate_ad_text"
                    ):
                        with st.spinner("Генерирую маркетинговые материалы для карточки товара и рекламы..."):
                            marketing_content = generate_marketing_content(product_name, strengths, weaknesses)

                        st.session_state.marketing_content = marketing_content
                        st.session_state.content_generated = True
                        st.rerun()

                # Отображаем результат, если он уже сгенерирован
                if 'content_generated' in st.session_state and st.session_state.content_generated:
                    st.caption(
                        "Используйте эти материалы как рабочую основу: перед публикацией проверьте факты, ограничения площадки и соответствие реальным свойствам товара."
                    )
                    st.markdown(st.session_state.marketing_content)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # Текст для скачивания
                    download_text = f"""Текст для карточки и рекламы
                Товар: {product_name}
                Артикул: {current_sku}

                {st.session_state.marketing_content}
                """

                    col1, col2 = st.columns([1, 1])

                    with col1:
                        st.download_button(
                            label="Скачать текст",
                            data=download_text.encode("utf-8"),
                            file_name=f"marketing_content_{current_sku}.txt",
                            mime="text/plain",
                            width="stretch",
                            icon=":material/download:",
                            key="download_ad_text"
                        )

                    with col2:
                        if st.button(
                                "Сгенерировать другой вариант",
                                width="stretch",
                                icon=":material/refresh:",
                                key="regenerate_ad_text"
                        ):
                            with st.spinner("Генерирую другой вариант текста..."):
                                marketing_content = generate_marketing_content(product_name, strengths, weaknesses)

                            st.session_state.marketing_content = marketing_content
                            st.session_state.content_generated = True
                            st.rerun()
            # 3. Исходные отзывы
            with st.expander("Подробная статистика отзывов"):
                if reviews_df is not None and not reviews_df.empty:
                    # Применяем цветовое форматирование к тональности
                    styled_reviews = reviews_df.style.map(color_sentiment, subset=['sentiment'])
                    st.dataframe(styled_reviews, width="stretch")
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
    **ИнСайт Бот** — это сервис для анализа отзывов Wildberries и подготовки маркетинговых материалов на основе реальных мнений покупателей.

    Сервис помогает маркетологу:
    - быстро собрать отзывы по артикулу или ссылке;
    - определить общую тональность отзывов;
    - выделить ключевые преимущества и слабые места товара;
    - понять, какие возражения покупателей нужно закрывать;
    - подготовить рекламный текст для объявления или карточки товара;
    - сохранить результаты анализа в базе данных.

    **Используемые технологии:**
    - **BERT-модель** — классификация отзывов по тональности;
    - **SHAP-анализ** — выделение наиболее информативных отзывов;
    - **GigaChat API** — генерация рекламного текста;
    - **PostgreSQL** — хранение товаров, отзывов и результатов анализа;
    - **Streamlit** — веб-интерфейс сервиса.
    """)
    with st.expander("Правовой режим и качество данных", expanded=False):
        st.markdown(f"""
        Сервис анализирует только открыто отображаемые отзывы и товарные данные Wildberries.

        В базу данных не сохраняются:
        - имена покупателей;
        - профили пользователей;
        - фотографии пользователей;
        - номера телефонов, адреса и иные персональные данные.

        Для повышения качества аналитики сервис:
        - не проводит анализ товаров, если найдено меньше **{MIN_REVIEWS_FOR_ANALYSIS}** содержательных отзывов;
        - исключает слишком короткие, дублирующиеся и шаблонные отзывы;
        - использует результаты в агрегированном виде: доли тональности, ключевые плюсы, минусы и маркетинговые рекомендации.

        Отдельный модуль точного определения AI-сгенерированных отзывов не используется, так как это самостоятельная исследовательская задача. 
        Вместо этого применяется фильтрация подозрительных и малоинформативных текстов.
        """)