import os
import io
import re
import gzip
import json
import streamlit as st
import pandas as pd
import psycopg2
from PIL import Image
import plotly.express as px
import requests
import uuid
import time
from requests.exceptions import SSLError, ConnectionError, Timeout
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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

# Модель BERT для анализа тональности отзывов.
# При необходимости можно переопределить в .streamlit/secrets.toml:
# HF_MODEL_ID = "ваш_логин/ваша_модель"
MODEL_ID = st.secrets.get("HF_MODEL_ID", "fsed/bert-review-sentiment-classifier")



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
def request_with_retries(method, url, max_attempts=4, timeout=60, **kwargs):
    """
    Выполняет HTTP-запрос с повторными попытками.
    Нужно для GigaChat, потому что соединение иногда сбрасывается сервером.
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                timeout=timeout,
                **kwargs
            )

            # Повторяем запрос при временных ошибках сервера
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"

                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                    continue

            return response

        except (SSLError, ConnectionError, Timeout) as e:
            last_error = e

            if attempt < max_attempts:
                time.sleep(2 * attempt)
                continue

            raise

    raise RuntimeError(f"Не удалось выполнить запрос после нескольких попыток: {last_error}")

def generate_marketing_content(product_name, strengths, weaknesses):
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

        response = request_with_retries(
            "POST",
            token_url,
            headers=headers,
            data=payload,
            verify=False,
            timeout=20,
            max_attempts=3
        )


        if response.status_code != 200:
            return f"Ошибка при получении токена ({response.status_code}): {response.text}"

        access_token = response.json().get('access_token')
        if not access_token:
            return f"Не удалось получить access_token: {response.text}"

        # Шаг 2: Готовим промпт
        prompt = f"""
        Ты — профессиональный копирайтер и маркетолог для карточек товаров на маркетплейсах.

        Твоя задача — на основе анализа отзывов покупателей создать релевантный рекламный текст для объявления товара.

        ТОВАР:
        {product_name}

        СИЛЬНЫЕ СТОРОНЫ ТОВАРА ПО ОТЗЫВАМ:
        {', '.join(strengths) if strengths else 'Не выявлено'}

        СЛАБЫЕ СТОРОНЫ ТОВАРА ПО ОТЗЫВАМ:
        {', '.join(weaknesses) if weaknesses else 'Не выявлено'}

        Сформируй готовый текст для объявления, а не аналитический отчет.

        Структура ответа:

        1. Заголовок объявления
        Короткий цепляющий заголовок до 70 символов.

        2. Основной рекламный текст
        Предложения, которые можно использовать в описании товара или рекламном объявлении.

        3. Ключевые преимущества
        5 коротких буллитов для карточки товара или инфографики.

        4. Короткий вариант для рекламы
        Предложения для баннера, таргетированной рекламы или промопоста.

        5. Призыв к действию
        Фраза, побуждающая купить или перейти к товару.

        Правила:
        - Не пиши слово "отчет".
        - Не пиши аналитические выводы.
        - Не упоминай, что текст создан на основе отзывов.
        - Не обещай того, чего нет в сильных сторонах товара.
        - Слабые стороны учитывай аккуратно: не называй их прямо, а обходи через нейтральные формулировки.
        - Пиши живым, понятным и продающим языком.
        - Текст должен быть на русском языке.
        - Используй Markdown для удобного отображения.
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
        chat_response = request_with_retries(
            "POST",
            chat_url,
            headers=chat_headers,
            json=chat_payload,
            verify=False,
            timeout=90,
            max_attempts=4
        )

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
        query = """
        SELECT review_text, sentiment, confidence 
        FROM reviews 
        WHERE nm_id = %s
        """
        df = pd.read_sql(query, conn, params=(str(nm_id),))
        conn.close()
        return df
    except Exception as e:
        st.error(f"Ошибка при загрузке отзывов: {e}")
        return None

def get_all_products():
    try:
        conn = get_db_connection()
        # Используем обновленные названия колонок: category_name
        df = pd.read_sql("SELECT nm_id, category_name, product_name, product_url FROM products", conn)
        conn.close()

        # Важно: после загрузки данных из WB артикул может прийти из БД числом,
        # а в session_state хранится строкой. Приводим всё к строкам, чтобы поиск
        # выбранного товара не падал с IndexError.
        if not df.empty:
            df["nm_id"] = df["nm_id"].astype(str).str.strip()
            df["category_name"] = df["category_name"].fillna("Без категории").astype(str).str.strip()
            df["product_name"] = df["product_name"].fillna("").astype(str).str.strip()
            df["product_url"] = df["product_url"].fillna("").astype(str).str.strip()
            df.loc[df["product_name"] == "", "product_name"] = "Товар " + df["nm_id"]
            df.loc[df["category_name"] == "", "category_name"] = "Без категории"

        return df
    except Exception as e:
        st.error(f"Ошибка при загрузке списка товаров: {e}")
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

def parse_summary_stats(summary_text):
    """Извлекает числовые показатели из текстового резюме товара."""
    stats = {
        "total": 0,
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "positive_share": 0.0,
        "negative_share": 0.0,
        "neutral_share": 0.0,
    }

    if not summary_text:
        return stats

    patterns = {
        "total": r"Всего обработано отзывов:\s*(\d+)",
        "positive": r"Позитивные отзывы:\s*(\d+)\s*\(([\d.,]+)%",
        "negative": r"Негативные отзывы:\s*(\d+)\s*\(([\d.,]+)%",
        "neutral": r"Нейтральные отзывы:\s*(\d+)\s*\(([\d.,]+)%",
    }

    total_match = re.search(patterns["total"], summary_text)
    if total_match:
        stats["total"] = int(total_match.group(1))

    for key, count_field, share_field in [
        ("positive", "positive_count", "positive_share"),
        ("negative", "negative_count", "negative_share"),
        ("neutral", "neutral_count", "neutral_share"),
    ]:
        match = re.search(patterns[key], summary_text)
        if match:
            stats[count_field] = int(match.group(1))
            stats[share_field] = float(match.group(2).replace(",", "."))

    return stats


def build_marketing_recommendations(stats, strengths, weaknesses):
    """Формирует понятные рекомендации для маркетолога."""
    recommendations = []

    positive_share = stats.get("positive_share", 0)
    negative_share = stats.get("negative_share", 0)
    total = stats.get("total", 0)

    if total < 30:
        recommendations.append(
            "Данных пока немного: выводы лучше использовать как предварительные. "
            "Для более точной картины желательно собрать больше отзывов."
        )

    if positive_share >= 80:
        recommendations.append(
            "У товара сильный позитивный фон. В рекламе можно делать акцент на доверии покупателей, качестве и подтверждённых преимуществах."
        )
    elif positive_share >= 60:
        recommendations.append(
            "Товар воспринимается преимущественно положительно, но в коммуникации стоит аккуратно закрывать возможные сомнения покупателей."
        )
    else:
        recommendations.append(
            "Позитивный фон выражен умеренно. Перед активным продвижением стоит проверить карточку товара, описание, ожидания покупателей и повторяющиеся претензии."
        )

    if negative_share >= 15:
        recommendations.append(
            "Доля негативных отзывов заметная. Рекомендуется использовать минусы как список возражений: уточнить описание, добавить предупреждения, улучшить инфографику и ответы на вопросы."
        )
    elif negative_share > 0:
        recommendations.append(
            "Негативные отзывы есть, но их доля невысокая. Их можно использовать для точечной доработки карточки и рекламных формулировок."
        )
    else:
        recommendations.append(
            "Существенный негатив по отзывам не выделен. Основной упор можно сделать на преимущества и сценарии использования товара."
        )

    if strengths:
        recommendations.append(
            "Главные преимущества для карточки товара: " + "; ".join(strengths[:3]) + "."
        )

    if weaknesses:
        recommendations.append(
            "Что стоит учесть в описании и рекламе: " + "; ".join(weaknesses[:3]) + "."
        )

    return recommendations


def build_ad_brief(product_name, strengths, weaknesses, stats):
    """Готовит краткий бриф для маркетолога."""
    positive_share = stats.get("positive_share", 0)
    negative_share = stats.get("negative_share", 0)

    if positive_share >= 80:
        tone = "уверенный, позитивный, с акцентом на качество и довольных покупателей"
    elif negative_share >= 15:
        tone = "аккуратный, объясняющий, с проработкой возражений"
    else:
        tone = "нейтрально-продающий, с акцентом на практическую пользу"

    main_strengths = "; ".join(strengths[:5]) if strengths else "преимущества выражены слабо"
    main_risks = "; ".join(weaknesses[:5]) if weaknesses else "существенные риски не выявлены"

    return f"""Краткий маркетинговый бриф

Товар: {product_name}

Рекомендуемый тон коммуникации:
{tone}

Что выносить в рекламу:
{main_strengths}

Какие возражения закрывать:
{main_risks}

Рекомендация:
Использовать сильные стороны в заголовках, карточке товара, инфографике и рекламных объявлениях. Слабые стороны не выносить напрямую в рекламу, а закрывать через уточняющие формулировки, честное описание комплектации, назначения и ожидаемого результата.
"""


def marketing_report_to_excel_bytes(product_name, current_sku, summary_text, reviews_df, strengths, weaknesses, recommendations):
    """Формирует Excel-отчёт для скачивания маркетологом."""
    output = io.BytesIO()

    summary_rows = [
        ["Товар", product_name],
        ["Артикул", current_sku],
        ["", ""],
        ["Сводная аналитика", summary_text],
        ["", ""],
        ["Ключевые плюсы", "\n".join(strengths) if strengths else "Не выявлено"],
        ["Ключевые минусы", "\n".join(weaknesses) if weaknesses else "Не выявлено"],
        ["", ""],
        ["Рекомендации", "\n".join(recommendations) if recommendations else "Нет рекомендаций"],
    ]

    summary_df = pd.DataFrame(summary_rows, columns=["Показатель", "Значение"])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="summary")

        if reviews_df is not None and not reviews_df.empty:
            export_reviews = reviews_df.copy()
            export_reviews["sentiment_label"] = export_reviews["sentiment"].map({
                0: "Нейтральный",
                1: "Негативный",
                2: "Позитивный"
            })
            export_reviews.to_excel(writer, index=False, sheet_name="reviews")

    return output.getvalue()
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


# --- ФУНКЦИИ ДЛЯ ЗАГРУЗКИ И АНАЛИЗА ПОЛЬЗОВАТЕЛЬСКИХ ФАЙЛОВ ---
def normalize_column_name(name):
    """Приводит название колонки к единому виду для поиска нужных полей."""
    return re.sub(r"[^a-zа-яё0-9]+", "", str(name).strip().lower())


def find_column(df, candidates):
    """Ищет колонку в DataFrame по нескольким возможным вариантам названий."""
    normalized_map = {normalize_column_name(col): col for col in df.columns}

    for candidate in candidates:
        key = normalize_column_name(candidate)
        if key in normalized_map:
            return normalized_map[key]

    return None


def read_uploaded_reviews_file(uploaded_file):
    """Читает CSV/XLSX с отзывами. CSV поддерживает разделители ; , и табуляцию."""
    raw = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()

    if filename.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(raw))

    if filename.endswith(".csv"):
        # Сначала пробуем типичный файл из JS-скрипта Wildberries: UTF-8 BOM + ;
        attempts = [
            {"sep": ";", "encoding": "utf-8-sig"},
            {"sep": ",", "encoding": "utf-8-sig"},
            {"sep": "\t", "encoding": "utf-8-sig"},
            {"sep": ";", "encoding": "cp1251"},
            {"sep": ",", "encoding": "cp1251"},
        ]

        best_df = None
        for params in attempts:
            try:
                df = pd.read_csv(io.BytesIO(raw), **params)
                if best_df is None or df.shape[1] > best_df.shape[1]:
                    best_df = df
                if df.shape[1] >= 2:
                    return df
            except Exception:
                continue

        if best_df is not None:
            return best_df

    raise ValueError("Не удалось прочитать файл. Поддерживаются CSV и XLSX.")


@st.cache_resource(show_spinner=False)
def load_sentiment_model():
    """Загружает BERT-модель один раз и кеширует её для Streamlit."""
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    model.eval()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    return tokenizer, model, device


def predict_sentiment_batch(texts, max_length=256, batch_size=16, return_probs=False):
    """
    Пакетно определяет тональность отзывов.

    Классы модели:
    0 — нейтрально
    1 — негативно
    2 — позитивно

    Логика перенесена из рабочего ноутбука:
    тексты обрабатываются батчами, вероятности считаются через softmax.
    """
    import torch
    import numpy as np

    tokenizer, model, device = load_sentiment_model()

    if isinstance(texts, str):
        texts = [texts]

    texts = [str(t) for t in texts]

    all_preds = []
    all_probs = []

    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start:start + batch_size]

        encoded = tokenizer(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt"
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}

        with torch.no_grad():
            outputs = model(**encoded)
            batch_probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()
            batch_preds = np.argmax(batch_probs, axis=1)

        all_preds.extend(batch_preds.tolist())
        all_probs.extend(batch_probs.tolist())

    probs_array = np.array(all_probs)

    confidences = []
    for pred, probs in zip(all_preds, probs_array):
        confidences.append(round(float(probs[int(pred)]), 4))

    if return_probs:
        return all_preds, confidences, probs_array

    return all_preds, confidences


def predict_positive_probability_for_shap(texts, max_length=256):
    """
    Возвращает вероятность положительного класса.
    Нужна для SHAP-анализа, как в рабочем ноутбуке.
    """
    import torch
    import numpy as np

    tokenizer, model, device = load_sentiment_model()

    if isinstance(texts, str):
        texts = [texts]

    processed = []
    for text in texts:
        if isinstance(text, list):
            processed.append(" ".join(str(x) for x in text))
        else:
            processed.append(str(text))

    encoded = tokenizer(
        processed,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt"
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}

    with torch.no_grad():
        outputs = model(**encoded)
        probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()

    if probs.ndim == 2 and probs.shape[1] >= 3:
        return probs[:, 2]

    # Защита на случай другой конфигурации модели.
    return np.max(probs, axis=1)


@st.cache_resource(show_spinner=False)
def load_shap_explainer():
    """
    Создает SHAP explainer для выбора наиболее характерных плюсов и минусов.
    Если shap не установлен на сервере, возвращает None — тогда сработает резервная логика.
    """
    try:
        import shap

        masker = shap.maskers.Text(tokenizer=r"\W+")
        return shap.Explainer(predict_positive_probability_for_shap, masker=masker)
    except Exception:
        return None


def normalize_review_point(text, max_len=260):
    """Очищает текст инсайта, но не превращает его в слишком короткую фразу."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    text = text.strip(" .,!?:;—-")

    if not text:
        return ""

    # Отсекаем совсем неинформативные фразы вроде «1», «не чего», «кошмар».
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text)
    if len(text) < 18 or len(words) < 3:
        return ""

    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].strip() + "..."

    return text


def unique_nonempty_points(points, limit=5):
    """Убирает пустые значения и дубли с сохранением порядка."""
    result = []
    seen = set()

    for point in points:
        cleaned = normalize_review_point(point)
        if not cleaned:
            continue

        key = cleaned.lower()
        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

        if len(result) >= limit:
            break

    return result


def fallback_pros_cons_from_reviews(group_df, top_k=5):
    """
    Резервный способ выбора плюсов/минусов, если SHAP недоступен.
    Выбирает более содержательные отзывы, а не самые короткие и не только по confidence.
    """
    df = group_df.copy()
    df["review_text"] = df["review_text"].fillna("").astype(str)
    df["text_len"] = df["review_text"].str.len()

    positive_candidates = (
        df[(df["sentiment"] == 2) & (df["text_len"] >= 40)]
        .sort_values(["confidence", "text_len"], ascending=[False, False])["review_text"]
        .tolist()
    )

    negative_candidates = (
        df[(df["sentiment"] == 1) & (df["text_len"] >= 25)]
        .sort_values(["confidence", "text_len"], ascending=[False, False])["review_text"]
        .tolist()
    )

    # Если негативных отзывов мало, берем отзывы с низкой позитивной вероятностью / нейтральные.
    if len(negative_candidates) < top_k and "prob_pos" in df.columns:
        extra = (
            df[(df["sentiment"].isin([0, 1])) & (df["text_len"] >= 25)]
            .sort_values(["prob_pos", "text_len"], ascending=[True, False])["review_text"]
            .tolist()
        )
        negative_candidates.extend(extra)

    pros = unique_nonempty_points(positive_candidates, limit=top_k)
    cons = unique_nonempty_points(negative_candidates, limit=top_k)

    return pros, cons


def pros_cons_from_reviews(texts, n_samples=50, top_k=5):
    """
    Извлекает ключевые плюсы и минусы по логике из рабочего ноутбука:
    SHAP оценивает вклад текста в вероятность положительного класса,
    затем выбираются отзывы с самым сильным положительным и отрицательным вкладом.
    """
    import random
    import numpy as np

    valid_texts = []
    for text in texts:
        cleaned = normalize_review_point(text, max_len=1000)
        if cleaned:
            valid_texts.append(cleaned)

    if not valid_texts:
        return [], []

    if len(valid_texts) > n_samples:
        # Фиксированный seed нужен, чтобы один и тот же товар не менял инсайты при каждом запуске.
        texts_for_shap = random.Random(42).sample(valid_texts, n_samples)
    else:
        texts_for_shap = valid_texts

    explainer = load_shap_explainer()
    if explainer is None:
        return [], []

    try:
        shap_values = explainer(texts_for_shap)
    except Exception:
        return [], []

    scored_sentences = []

    for index, example in enumerate(shap_values):
        total_impact = float(np.sum(example.values))
        clean_text = normalize_review_point(texts_for_shap[index], max_len=300)

        if clean_text:
            scored_sentences.append((clean_text, total_impact))

    pros_raw = sorted(scored_sentences, key=lambda item: item[1], reverse=True)
    cons_raw = sorted(scored_sentences, key=lambda item: item[1])

    pros = unique_nonempty_points([text for text, score in pros_raw if score > 0.1], limit=top_k)
    cons = unique_nonempty_points([text for text, score in cons_raw if score < 0], limit=top_k)

    return pros, cons


def build_summary_text(product_name, group_df, product_category=""):
    """
    Формирует текстовую аналитику в формате, который уже понимает блок генерации объявления.

    Важно: плюсы и минусы теперь строятся не из первых коротких отзывов,
    а по SHAP-логике из рабочего ноутбука, поэтому инсайты становятся содержательнее.
    """
    total = len(group_df)
    positive_count = int((group_df["sentiment"] == 2).sum())
    negative_count = int((group_df["sentiment"] == 1).sum())
    neutral_count = int((group_df["sentiment"] == 0).sum())

    positive_share = round(positive_count / total * 100, 1) if total else 0
    negative_share = round(negative_count / total * 100, 1) if total else 0
    neutral_share = round(neutral_count / total * 100, 1) if total else 0

    # Основной способ — SHAP, как в рабочем ноутбуке.
    pros, cons = pros_cons_from_reviews(
        group_df["review_text"].fillna("").astype(str).tolist(),
        n_samples=min(50, total),
        top_k=5
    )

    # Резервный способ, если shap не установлен или не смог обработать тексты.
    if len(pros) < 3 or len(cons) < 2:
        fallback_pros, fallback_cons = fallback_pros_cons_from_reviews(group_df, top_k=5)

        if len(pros) < 3:
            pros = unique_nonempty_points(pros + fallback_pros, limit=5)

        if len(cons) < 2:
            cons = unique_nonempty_points(cons + fallback_cons, limit=5)

    if not pros:
        pros = ["Позитивные особенности товара по загруженным отзывам выражены слабо"]

    if not cons:
        cons = ["Существенные повторяющиеся минусы по загруженным отзывам не выявлены"]

    plus_lines = "\n".join(f"{idx}. {point}" for idx, point in enumerate(pros, start=1))
    minus_lines = "\n".join(f"{idx}. {point}" for idx, point in enumerate(cons, start=1))

    category_line = f"Категория: {product_category}\n" if product_category else ""

    return f"""АНАЛИТИКА ПО ТОВАРУ: {product_name}
{category_line}
Всего обработано отзывов: {total}
Позитивные отзывы: {positive_count} ({positive_share}%)
Негативные отзывы: {negative_count} ({negative_share}%)
Нейтральные отзывы: {neutral_count} ({neutral_share}%)

КЛЮЧЕВЫЕ ПЛЮСЫ:
{plus_lines}

КЛЮЧЕВЫЕ МИНУСЫ:
{minus_lines}
"""

def prepare_uploaded_reviews_dataframe(df):
    """Приводит пользовательский файл к единой структуре для анализа и записи в БД."""
    nm_col = find_column(df, ["nmId", "nm_id", "nm id", "артикул", "артикул товара", "sku", "id"])
    text_col = find_column(df, ["text", "review_text", "review", "comment", "отзыв", "отзывы", "текст", "текст отзыва", "комментарий"])
    rating_col = find_column(df, ["rating", "оценка", "рейтинг", "stars", "звезды"])
    product_name_col = find_column(df, ["product_name", "product name", "productName", "name", "название", "название товара", "товар"])
    category_col = find_column(df, ["category_name", "category", "categoryName", "категория", "категория товара", "subjectName"])
    url_col = find_column(df, ["product_url", "product url", "url", "link", "ссылка", "ссылка товара"])

    if nm_col is None:
        raise ValueError("В файле не найдена колонка с артикулом товара. Нужна колонка nmId или nm_id.")
    if text_col is None:
        raise ValueError("В файле не найдена колонка с текстом отзыва. Нужна колонка text или review_text.")

    result = pd.DataFrame()
    result["nm_id"] = df[nm_col].astype(str).str.strip()
    result["review_text"] = df[text_col].fillna("").astype(str).str.strip()

    result["rating"] = df[rating_col] if rating_col else None
    result["product_name"] = df[product_name_col] if product_name_col else None
    result["category_name"] = df[category_col] if category_col else None
    result["product_url"] = df[url_col] if url_col else None

    result = result[(result["nm_id"] != "") & (result["nm_id"].str.lower() != "nan")]
    result = result[(result["review_text"] != "") & (result["review_text"].str.lower() != "nan")]

    if result.empty:
        raise ValueError("После очистки в файле не осталось строк с артикулом и текстом отзыва.")

    # Запасные значения, если пользовательский файл содержит только nmId и text.
    result["product_name"] = result.apply(
        lambda row: str(row["product_name"]).strip()
        if pd.notna(row["product_name"]) and str(row["product_name"]).strip() and str(row["product_name"]).lower() != "nan"
        else f"Товар {row['nm_id']}",
        axis=1
    )
    result["category_name"] = result.apply(
        lambda row: str(row["category_name"]).strip()
        if pd.notna(row["category_name"]) and str(row["category_name"]).strip() and str(row["category_name"]).lower() != "nan"
        else "Загруженные данные",
        axis=1
    )
    result["product_url"] = result.apply(
        lambda row: str(row["product_url"]).strip()
        if pd.notna(row["product_url"]) and str(row["product_url"]).strip() and str(row["product_url"]).lower() != "nan"
        else f"https://www.wildberries.ru/catalog/{row['nm_id']}/detail.aspx",
        axis=1
    )

    return result.reset_index(drop=True)


def analyze_uploaded_reviews(df):
    """Анализирует отзывы из файла BERT-моделью и готовит сводки по товарам."""
    prepared_df = prepare_uploaded_reviews_dataframe(df)
    texts = prepared_df["review_text"].tolist()

    sentiments, confidences = predict_sentiment_batch(texts)
    prepared_df["sentiment"] = sentiments
    prepared_df["confidence"] = confidences
    prepared_df["sentiment_label"] = prepared_df["sentiment"].map({0: "Нейтральный", 1: "Негативный", 2: "Позитивный"})

    product_summaries = []
    for nm_id, group in prepared_df.groupby("nm_id"):
        first_row = group.iloc[0]
        product_summaries.append({
            "nm_id": str(nm_id),
            "product_name": str(first_row["product_name"]),
            "category_name": str(first_row["category_name"]),
            "product_url": str(first_row["product_url"]),
            "summary_text": build_summary_text(str(first_row["product_name"]), group, str(first_row["category_name"])),
            "chart_html": ""
        })

    return prepared_df, product_summaries


def save_uploaded_analysis_to_db(analyzed_df, product_summaries):
    """Сохраняет товары, отзывы и сводную аналитику в PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for item in product_summaries:
            nm_id = item["nm_id"]

            cursor.execute("SELECT 1 FROM products WHERE nm_id = %s", (nm_id,))
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE products
                    SET category_name = %s,
                        product_name = %s,
                        product_url = %s
                    WHERE nm_id = %s
                    """,
                    (item["category_name"], item["product_name"], item["product_url"], nm_id)
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO products (nm_id, category_name, product_name, product_url)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (nm_id, item["category_name"], item["product_name"], item["product_url"])
                )

            cursor.execute("SELECT 1 FROM product_summary WHERE nm_id = %s", (nm_id,))
            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE product_summary
                    SET summary_text = %s,
                        chart_html = %s
                    WHERE nm_id = %s
                    """,
                    (item["summary_text"], item["chart_html"], nm_id)
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO product_summary (nm_id, summary_text, chart_html)
                    VALUES (%s, %s, %s)
                    """,
                    (nm_id, item["summary_text"], item["chart_html"])
                )

            # Для загруженного товара заменяем старые отзывы новыми, чтобы аналитика не дублировалась.
            cursor.execute("DELETE FROM reviews WHERE nm_id = %s", (nm_id,))

        for _, row in analyzed_df.iterrows():
            cursor.execute(
                """
                INSERT INTO reviews (nm_id, review_text, sentiment, confidence)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    str(row["nm_id"]),
                    str(row["review_text"]),
                    int(row["sentiment"]),
                    float(row["confidence"])
                )
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def dataframe_to_excel_bytes(df):
    """Готовит Excel-файл с результатами анализа для скачивания."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="analysis")
    return output.getvalue()



# --- ФУНКЦИИ ДЛЯ ПОИСКА И СБОРА ОТЗЫВОВ WILDBERRIES ПО АРТИКУЛУ/ССЫЛКЕ ---
WB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def wb_request_json(url: str, timeout: int = 25) -> Any:
    """Запрашивает JSON у публичных endpoint Wildberries."""
    request = Request(
        url,
        headers={
            "User-Agent": WB_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Encoding": "gzip",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))


def extract_wb_nm_id(value: str) -> int:
    """Извлекает nmId из артикула или ссылки Wildberries."""
    match = re.search(r"/catalog/(\d+)/", str(value)) or re.search(r"\b(\d{6,})\b", str(value))
    if not match:
        raise ValueError(f"Не удалось найти артикул WB в строке: {value}")
    return int(match.group(1))


def wb_basket_hosts() -> list[str]:
    return [f"basket-{i:02d}.wbbasket.ru" for i in range(1, 41)]


def get_wb_card(nm_id: int) -> tuple[dict[str, Any], str]:
    """Получает card.json товара через wbbasket."""
    vol = nm_id // 100000
    part = nm_id // 1000
    last_error = None

    for host in wb_basket_hosts():
        url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
        try:
            data = wb_request_json(url)
            if isinstance(data, dict):
                return data, url
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc

    raise RuntimeError(f"Не удалось получить card.json для nmId={nm_id}. Последняя ошибка: {last_error}")


def get_wb_card_api_product(nm_id: int) -> dict[str, Any]:
    """Резервно получает данные карточки через card.wb.ru."""
    urls = [
        f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={nm_id}",
        f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&nm={nm_id}",
    ]

    for url in urls:
        try:
            data = wb_request_json(url)
            product = data.get("data", {}).get("products", [None])[0]
            if isinstance(product, dict):
                return product
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, IndexError, AttributeError):
            continue

    return {}


def get_wb_feedbacks(imt_id: int) -> tuple[dict[str, Any], str]:
    """Получает отзывы товара по imtId."""
    urls = [
        f"https://feedbacks1.wb.ru/feedbacks/v1/{imt_id}",
        f"https://feedbacks2.wb.ru/feedbacks/v1/{imt_id}",
    ]
    last_error = None

    for url in urls:
        try:
            data = wb_request_json(url)
            if isinstance(data, dict) and "feedbacks" in data:
                return data, url
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc
        time.sleep(0.4)

    raise RuntimeError(f"Не удалось получить отзывы для imtId={imt_id}. Последняя ошибка: {last_error}")


def first_text(*values: Any) -> str:
    """Возвращает первое непустое текстовое значение."""
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return re.sub(r"\s+", " ", text)
    return ""


def build_wb_product_url(nm_id: int) -> str:
    return f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"


def extract_wb_product_info(nm_id: int, card: dict[str, Any]) -> dict[str, Any]:
    """Достаёт название, категорию, ссылку и imtId товара."""
    api_product = get_wb_card_api_product(nm_id)
    selling = card.get("selling") or {}

    imt_id = first_text(
        card.get("imt_id"),
        card.get("imtId"),
        api_product.get("imtId"),
        api_product.get("imt_id"),
    )

    product_name = first_text(
        card.get("imt_name"),
        card.get("imtName"),
        card.get("product_name"),
        api_product.get("name"),
        api_product.get("productName"),
        f"Товар {nm_id}",
    )

    # Главная категория. Приоритет — корневые поля, чтобы получать «Красота», «Одежда» и т.п.
    category_name = first_text(
        card.get("subj_root_name"),
        card.get("subject_root_name"),
        card.get("root_name"),
        card.get("parent_name"),
        card.get("parentCategoryName"),
        api_product.get("subjectRootName"),
        api_product.get("rootName"),
        api_product.get("parentName"),
        card.get("subj_name"),
        card.get("subjectName"),
        card.get("subject_name"),
        api_product.get("subjectName"),
        api_product.get("subject"),
        card.get("kind_name"),
        selling.get("category_name"),
        "Wildberries",
    )

    return {
        "nmId": nm_id,
        "imt_id": int(imt_id) if str(imt_id).isdigit() else None,
        "product_name": product_name,
        "category_name": category_name,
        "product_url": build_wb_product_url(nm_id),
    }


def make_wb_review_text(feedback: dict[str, Any]) -> str:
    """Собирает единый текст отзыва из плюсов, минусов и комментария."""
    pros = first_text(feedback.get("pros"))
    cons = first_text(feedback.get("cons"))
    comment = first_text(feedback.get("text"))
    return first_text(" ".join(part for part in [pros, cons, comment] if part))


def flatten_wb_feedback_for_app(
    feedback: dict[str, Any],
    product_info: dict[str, Any],
    min_text_length: int,
) -> dict[str, Any] | None:
    text = make_wb_review_text(feedback)
    if len(text) < min_text_length:
        return None

    return {
        "nmId": product_info["nmId"],
        "product_name": product_info["product_name"],
        "category_name": product_info["category_name"],
        "product_url": product_info["product_url"],
        "rating": feedback.get("productValuation") or "",
        "text": text,
    }


def parse_wb_products_input(raw_text: str) -> list[str]:
    """Разбирает пользовательский ввод: ссылки/артикулы через строки, пробелы, запятые или ;."""
    parts = re.split(r"[\n,;\t]+", raw_text.strip())
    result = []
    for part in parts:
        value = part.strip().strip('"').strip("'")
        if value:
            result.append(value)
    return result


def fetch_wb_reviews_dataframe(products: list[str], limit: int = 0, min_text_length: int = 20) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Собирает отзывы Wildberries по списку артикулов/ссылок и возвращает DataFrame
    в формате nmId, product_name, category_name, product_url, rating, text.
    """
    if not products:
        raise ValueError("Введите хотя бы один артикул или ссылку Wildberries.")

    nm_ids = []
    for product in products:
        nm_id = extract_wb_nm_id(product)
        if nm_id not in nm_ids:
            nm_ids.append(nm_id)

    all_rows = []
    fetch_report = []

    for nm_id in nm_ids:
        card, card_url = get_wb_card(nm_id)
        product_info = extract_wb_product_info(nm_id, card)

        imt_id = product_info.get("imt_id")
        if not imt_id:
            raise RuntimeError(f"Для артикула {nm_id} не найден imtId, поэтому отзывы получить нельзя.")

        feedback_data, feedback_url = get_wb_feedbacks(int(imt_id))
        feedbacks = feedback_data.get("feedbacks") or []
        found_total = len(feedbacks)

        if limit and limit > 0:
            feedbacks = feedbacks[:limit]

        rows_for_product = []
        for item in feedbacks:
            row = flatten_wb_feedback_for_app(item, product_info, min_text_length=min_text_length)
            if row is not None:
                rows_for_product.append(row)

        all_rows.extend(rows_for_product)
        fetch_report.append({
            "nmId": str(nm_id),
            "product_name": product_info["product_name"],
            "category_name": product_info["category_name"],
            "product_url": product_info["product_url"],
            "found_reviews": found_total,
            "saved_reviews": len(rows_for_product),
            "card_url": card_url,
            "feedback_url": feedback_url,
        })
        time.sleep(0.4)

    df = pd.DataFrame(all_rows, columns=["nmId", "product_name", "category_name", "product_url", "rating", "text"])
    return df, fetch_report

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

    if st.button("Поиск и анализ", icon=":material/search:", use_container_width=True):
        st.session_state.page = "Главная"

    if st.button("Аналитика", icon=":material/monitoring:", use_container_width=True):
        st.session_state.page = "Аналитика"

    if st.button("О проекте", icon=":material/info:", use_container_width=True):
        st.session_state.page = "О проекте"

# --- СТРАНИЦА: ГЛАВНАЯ ---
if st.session_state.page == "Главная":
    st.title("Поиск и анализ отзывов Wildberries")
    st.markdown(
        "<p style='color: #28a745; font-style: italic; margin-bottom: 25px;'>"
        "Введите артикул или ссылку на товар. Сервис соберёт отзывы Wildberries, "
        "определит тональность, выделит ключевые плюсы и минусы, а затем поможет "
        "подготовить рекламный текст и маркетинговые выводы."
        "</p>",
        unsafe_allow_html=True
    )

    # Метрики главной страницы
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
            color: #707070;
            margin-bottom: 20px;
        }
        </style>
        <div class="custom-text">
            Основной сценарий — запустить новый анализ товара по артикулу или ссылке. База ниже нужна как справочник уже обработанных товаров.
        </div>
        """,
        unsafe_allow_html=True
    )

    # Главный сценарий выводим первым и шире, база — рядом как второстепенный блок
    col_analyze, col_saved = st.columns([1.35, 1], gap="large")

    # --- ЛЕВАЯ КОЛОНКА: ОСНОВНОЙ СЦЕНАРИЙ — НОВЫЙ АНАЛИЗ ---
    with col_analyze:
        st.markdown("### Новый анализ товара")
        st.caption(
            "Введите артикул или ссылку Wildberries. Сервис соберёт отзывы, "
            "определит тональность, выделит ключевые плюсы и минусы и сохранит результат."
        )

        tab_wb_search, tab_file_upload = st.tabs(["Артикул / ссылка WB", "CSV / Excel"])

        with tab_wb_search:
            st.info(
                "Основной сценарий: вставьте артикул или ссылку Wildberries. "
                "После запуска сервис автоматически соберёт отзывы, обработает их BERT-моделью "
                "и сохранит результат в базу."
            )
            wb_products_text = st.text_area(
                "Артикул или ссылка Wildberries",
                placeholder=(
                    "175088486\n"
                    "https://www.wildberries.ru/catalog/175088486/detail.aspx"
                ),
                height=120,
                help="Можно указать один или несколько товаров: каждый артикул или ссылку с новой строки."
            )

            wb_limit = st.number_input(
                "Лимит отзывов на товар",
                min_value=0,
                max_value=5000,
                value=0,
                step=50,
                help="0 — собрать все найденные отзывы. Для быстрой проверки можно поставить 100–300."
            )

            wb_min_text_length = st.number_input(
                "Минимальная длина текста отзыва",
                min_value=1,
                max_value=500,
                value=20,
                step=1,
                help="Короткие отзывы без содержательного текста будут пропущены."
            )

            if st.button(
                    "Запустить анализ товара",
                    type="primary",
                    icon=":material/search:",
                    use_container_width=True,
                    key="process_wb_search"
            ):
                try:
                    products = parse_wb_products_input(wb_products_text)

                    with st.spinner("Собираю отзывы Wildberries, запускаю BERT-модель и сохраняю результат..."):
                        raw_df, fetch_report = fetch_wb_reviews_dataframe(
                            products,
                            limit=int(wb_limit),
                            min_text_length=int(wb_min_text_length)
                        )

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
                        f"по {len(product_summaries)} товар(ам). Результат сохранён в базу."
                    )

                except Exception as e:
                    st.error(f"Ошибка при сборе или анализе отзывов: {e}")

            if "wb_fetch_report" in st.session_state:
                with st.expander("Что было найдено на Wildberries", expanded=False):
                    st.dataframe(pd.DataFrame(st.session_state.wb_fetch_report), use_container_width=True, hide_index=True)

        with tab_file_upload:
            st.markdown("##### Анализ готового файла")
            st.caption(
                "Этот режим нужен, если отзывы уже собраны парсером или подготовлены вручную. "
                "Для обычного пользователя проще использовать вкладку с артикулом или ссылкой."
            )

            uploaded_files = st.file_uploader(
                "Перетащите файл с отзывами сюда",
                type=["csv", "xlsx"],
                accept_multiple_files=True,
                help="Поддерживаются CSV и Excel. Желательные колонки: nmId, product_name, category_name, product_url, rating, text."
            )

            if uploaded_files:
                for uploaded_file in uploaded_files:
                    st.success(f"Файл '{uploaded_file.name}' загружен")

                    if st.button(
                            f"Проанализировать и сохранить: {uploaded_file.name}",
                            type="primary",
                            icon=":material/database_upload:",
                            use_container_width=True,
                            key=f"process_upload_{uploaded_file.name}"
                    ):
                        try:
                            with st.spinner("Загружаю модель, анализирую отзывы и сохраняю данные в базу..."):
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
                                f"по {len(product_summaries)} товар(ам). Результат сохранён в базу."
                            )

                        except Exception as e:
                            st.error(f"Ошибка при обработке файла: {e}")

        if "upload_result_df" in st.session_state:
            st.download_button(
                label="Скачать обработанный файл",
                data=dataframe_to_excel_bytes(st.session_state.upload_result_df),
                file_name="analyzed_reviews.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                icon=":material/download:"
            )

            if st.button(
                    "Открыть аналитику по последнему обработанному товару",
                    use_container_width=True,
                    icon=":material/monitoring:"
            ):
                st.session_state.page = "Аналитика"
                st.rerun()

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
                                    use_container_width=True
                            ):
                                st.session_state.current_sku = normalize_sku(row['nm_id'])
                                st.session_state.current_category = category
                                st.rerun()

                if st.session_state.current_sku:
                    st.write("")
                    selected_name = get_product_name_by_sku(product_df, st.session_state.current_sku)
                    st.info(f"Выбран товар из базы: **{selected_name}**")

                    if st.button("Открыть сохранённую аналитику", type="primary", use_container_width=True):
                        st.session_state.page = "Аналитика"
                        st.rerun()
        else:
            st.info("База пока пустая. Начните с анализа товара по артикулу или ссылке Wildberries.")

    st.divider()

    # Таблица каталога
    st.subheader("База уже проанализированных товаров")
    st.caption("Этот список пополняется автоматически после анализа по артикулу, ссылке или загруженному файлу.")

    if not product_df.empty:
        display_list = product_df[['nm_id', 'product_name', 'category_name']].rename(
            columns={'nm_id': 'Артикул', 'product_name': 'Наименование', 'category_name': 'Категория'}
        )
        st.dataframe(display_list, use_container_width=True, hide_index=True)
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

            st.markdown(f"#### 📊 Отчет по товару: {product_name}")


            # СОЗДАЕМ ДВЕ КОЛОНКИ: ГРАФИК СЛЕВА, ТЕКСТ СПРАВА
            col_text, col_chart = st.columns([2, 1])

            # --- ЛЕВАЯ КОЛОНКА: КРУГОВАЯ ДИАГРАММА ---
            with col_chart:
                st.markdown('<div style="text-align: center; width: 100%; margin: 0 auto;">📈Распределение мнений по тональности</div>', unsafe_allow_html=True)

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

                stats = parse_summary_stats(summary_text)
                recommendations = build_marketing_recommendations(stats, strengths, weaknesses)
                ad_brief = build_ad_brief(product_name, strengths, weaknesses, stats)

                st.markdown("### Маркетинговая интерпретация")

                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Всего отзывов", stats["total"])
                kpi2.metric("Позитив", f'{stats["positive_share"]}%')
                kpi3.metric("Негатив", f'{stats["negative_share"]}%')
                kpi4.metric("Нейтрально", f'{stats["neutral_share"]}%')

                with st.expander("Рекомендации для маркетолога", expanded=True):
                    for rec in recommendations:
                        st.markdown(f"- {rec}")

                with st.expander("Краткий рекламный бриф", expanded=False):
                    st.text(ad_brief)

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
                    use_container_width=True,
                    icon=":material/download:"
                )

                # Проверяем, есть ли данные для генерации
                # Проверяем, есть ли данные для генерации
                if strengths or weaknesses:
                    st.caption(f"Найдено: {len(strengths)} сильных сторон и {len(weaknesses)} слабых сторон")

                    # Основная кнопка генерации
                    if st.button(
                            "Сгенерировать текст для объявления",
                            type="primary",
                            icon=":material/campaign:",
                            use_container_width=True,
                            key="generate_ad_text"
                    ):
                        with st.spinner("Генерирую рекламный текст для объявления..."):
                            marketing_content = generate_marketing_content(product_name, strengths, weaknesses)

                        st.session_state.marketing_content = marketing_content
                        st.session_state.content_generated = True
                        st.rerun()

                # Отображаем результат, если он уже сгенерирован
                if 'content_generated' in st.session_state and st.session_state.content_generated:
                    st.markdown("### 📝 Текст для объявления")
                    st.markdown(st.session_state.marketing_content)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # Текст для скачивания
                    download_text = f"""Текст для объявления

                Товар: {product_name}
                Артикул: {current_sku}

                {st.session_state.marketing_content}
                """

                    col1, col2 = st.columns([1, 1])

                    with col1:
                        st.download_button(
                            label="Скачать текст",
                            data=download_text.encode("utf-8"),
                            file_name=f"ad_text_{current_sku}.txt",
                            mime="text/plain",
                            use_container_width=True,
                            icon=":material/download:",
                            key="download_ad_text"
                        )

                    with col2:
                        if st.button(
                                "Сгенерировать другой вариант",
                                use_container_width=True,
                                icon=":material/refresh:",
                                key="regenerate_ad_text"
                        ):
                            with st.spinner("Генерирую другой вариант текста..."):
                                marketing_content = generate_marketing_content(product_name, strengths, weaknesses)

                            st.session_state.marketing_content = marketing_content
                            st.session_state.content_generated = True
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