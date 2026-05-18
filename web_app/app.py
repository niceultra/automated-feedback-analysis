import os
import io
import re
import streamlit as st
import pandas as pd
from PIL import Image
import plotly.express as px

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


# Модель BERT для анализа тональности отзывов.
# При необходимости можно переопределить в .streamlit/secrets.toml:
# HF_MODEL_ID = "ваш_логин/ваша_модель"
MODEL_ID = st.secrets.get("HF_MODEL_ID", "fsed/bert-review-sentiment-classifier")
HF_TOKEN = st.secrets.get("HF_TOKEN", None)
MIN_REVIEWS_FOR_ANALYSIS = 400


def generate_marketing_content(product_name, strengths, weaknesses):
    """Генерирует маркетинговый комплект через GigaChat."""
    client_id = st.secrets.get("GIGACHAT_CLIENT_ID", None)
    client_secret = st.secrets.get("GIGACHAT_CLIENT_SECRET", None)

    return generate_marketing_content_with_gigachat(
        product_name=product_name,
        strengths=strengths,
        weaknesses=weaknesses,
        client_id=client_id,
        client_secret=client_secret,
    )

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
    """
    Извлекает числовые показатели из текстового резюме товара.
    Поддерживает новый и старый формат summary_text.
    """
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

    text = str(summary_text)
    text = re.sub(r"\s+", " ", text).strip()

    def to_float(value):
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return 0.0

    # 1. Всего отзывов: поддержка старого и нового формата
    total_patterns = [
        r"Всего обработано отзывов:\s*(\d+)",
        r"Всего отзывов:\s*(\d+)",
    ]

    for pattern in total_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            stats["total"] = int(match.group(1))
            break

    # 2. Позитивные отзывы: новый формат + старый формат
    positive_patterns = [
        r"Позитивные отзывы:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
        r"Позитивных:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
        r"Позитивные:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
    ]

    for pattern in positive_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            stats["positive_count"] = int(match.group(1))
            stats["positive_share"] = to_float(match.group(2))
            break

    # 3. Негативные отзывы: новый формат + старый формат
    negative_patterns = [
        r"Негативные отзывы:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
        r"Негативных:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
        r"Негативные:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
    ]

    for pattern in negative_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            stats["negative_count"] = int(match.group(1))
            stats["negative_share"] = to_float(match.group(2))
            break

    # 4. Нейтральные отзывы: новый формат + старый формат
    neutral_patterns = [
        r"Нейтральные отзывы:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
        r"Нейтральных:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
        r"Нейтральные:\s*(\d+)\s*\(([\d.,]+)\s*%\)",
    ]

    for pattern in neutral_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            stats["neutral_count"] = int(match.group(1))
            stats["neutral_share"] = to_float(match.group(2))
            break

    # 5. Если проценты не найдены, но есть количество — пересчитываем вручную
    if stats["total"] > 0:
        if stats["positive_share"] == 0.0 and stats["positive_count"] > 0:
            stats["positive_share"] = round(stats["positive_count"] / stats["total"] * 100, 1)

        if stats["negative_share"] == 0.0 and stats["negative_count"] > 0:
            stats["negative_share"] = round(stats["negative_count"] / stats["total"] * 100, 1)

        if stats["neutral_share"] == 0.0 and stats["neutral_count"] > 0:
            stats["neutral_share"] = round(stats["neutral_count"] / stats["total"] * 100, 1)

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

    hf_kwargs = {"token": HF_TOKEN} if HF_TOKEN else {}

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, **hf_kwargs)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, **hf_kwargs)
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
    """Анализирует отзывы BERT-моделью и готовит сводки по товарам.

    Если по товару меньше MIN_REVIEWS_FOR_ANALYSIS отзывов,
    товар не анализируется и не сохраняется в базу.
    """
    prepared_df = prepare_uploaded_reviews_dataframe(df)

    review_counts = prepared_df.groupby("nm_id").size()

    valid_nm_ids = review_counts[
        review_counts >= MIN_REVIEWS_FOR_ANALYSIS
    ].index.astype(str).tolist()

    skipped_items = review_counts[
        review_counts < MIN_REVIEWS_FOR_ANALYSIS
    ]

    if not valid_nm_ids:
        details = "\n".join(
            f"— {nm_id}: {count} отзывов"
            for nm_id, count in skipped_items.items()
        )

        raise ValueError(
            f"Недостаточно отзывов для анализа. "
            f"Минимальный порог — {MIN_REVIEWS_FOR_ANALYSIS} отзывов на товар.\n\n"
            f"Найдено:\n{details}\n\n"
            f"Товар не был проанализирован и не сохранён в базу данных."
        )

    prepared_df = prepared_df[
        prepared_df["nm_id"].astype(str).isin(valid_nm_ids)
    ].reset_index(drop=True)

    if not skipped_items.empty:
        skipped_text = "\n".join(
            f"— {nm_id}: {count} отзывов"
            for nm_id, count in skipped_items.items()
        )

        st.warning(
            f"Некоторые товары пропущены, потому что по ним меньше "
            f"{MIN_REVIEWS_FOR_ANALYSIS} отзывов:\n\n{skipped_text}"
        )

    texts = prepared_df["review_text"].tolist()

    sentiments, confidences = predict_sentiment_batch(texts)
    prepared_df["sentiment"] = sentiments
    prepared_df["confidence"] = confidences
    prepared_df["sentiment_label"] = prepared_df["sentiment"].map({
        0: "Нейтральный",
        1: "Негативный",
        2: "Позитивный"
    })

    product_summaries = []

    for nm_id, group in prepared_df.groupby("nm_id"):
        first_row = group.iloc[0]

        product_summaries.append({
            "nm_id": str(nm_id),
            "product_name": str(first_row["product_name"]),
            "category_name": str(first_row["category_name"]),
            "product_url": str(first_row["product_url"]),
            "summary_text": build_summary_text(
                str(first_row["product_name"]),
                group,
                str(first_row["category_name"])
            ),
            "chart_html": ""
        })

    return prepared_df, product_summaries


def dataframe_to_excel_bytes(df):
    """Готовит Excel-файл с результатами анализа для скачивания."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="analysis")
    return output.getvalue()


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
                    width="stretch",
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
                            width="stretch",
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