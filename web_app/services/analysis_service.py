import io
import re
import streamlit as st
import pandas as pd
from services.review_quality_service import enrich_reviews_quality


# Модель BERT для анализа тональности отзывов.
# При необходимости можно переопределить в .streamlit/secrets.toml:
# HF_MODEL_ID = "ваш_логин/ваша_модель"
MODEL_ID = st.secrets.get("HF_MODEL_ID", "fsed/bert-review-sentiment-classifier")
HF_TOKEN = st.secrets.get("HF_TOKEN", None)

# Минимальный порог отзывов для анализа.
# Для Streamlit Cloud и WB endpoint лучше не ставить слишком высокое значение.
MIN_REVIEWS_FOR_ANALYSIS = int(st.secrets.get("MIN_REVIEWS_FOR_ANALYSIS", 400))


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
    Нужна для SHAP-анализа.
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

    return np.max(probs, axis=1)


@st.cache_resource(show_spinner=False)
def load_shap_explainer():
    """
    Создает SHAP explainer для выбора наиболее характерных плюсов и минусов.
    Если shap недоступен, возвращает None.
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

SHAP_PHRASE_STOPWORDS = set("""
и в во на но а я мы вы он она они оно это этот эта эти тот та те
тут там как что чтобы потому если или либо уже еще ещё очень просто
прямо вообще совсем реально товар товары вещь штука штуки заказ заказала
заказал купила купил брала брал пришел пришла пришло пришли спасибо
пожалуйста рекомендую советую
""".split())

SHAP_NEGATION_WORDS = {"не", "нет", "без", "ни"}


def _flatten_shap_values(values):
    """Приводит SHAP values к одномерному массиву."""
    import numpy as np

    arr = np.asarray(values, dtype=float)

    if arr.ndim == 0:
        return np.array([float(arr)])

    if arr.ndim == 1:
        return arr

    if arr.ndim == 2 and arr.shape[1] == 1:
        return arr[:, 0]

    return arr.reshape(arr.shape[0], -1).mean(axis=1)


def _token_to_text(token):
    """Приводит токен SHAP к обычному тексту."""
    text = str(token)
    text = text.replace("##", "")
    text = text.replace("▁", " ")
    text = text.replace("Ġ", " ")
    return text


def _tokens_to_phrase(tokens):
    """Собирает короткую фразу из токенов."""
    phrase = " ".join(_token_to_text(token) for token in tokens)
    phrase = re.sub(r"\s+", " ", phrase).strip()

    phrase = re.sub(r"\s+([.,!?;:%)])", r"\1", phrase)
    phrase = re.sub(r"([(])\s+", r"\1", phrase)

    phrase = phrase.strip(" .,!?:;—-–«»\"'()[]{}")
    phrase = phrase.lower()

    phrase = re.sub(r"^(и|а|но|это|всё|все|просто)\s+", "", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip()

    return phrase


def _phrase_words(phrase):
    return re.findall(r"[a-zа-яё0-9]+", str(phrase).lower())


def _is_meaningful_shap_phrase(phrase, max_words=8, max_chars=90):
    """Проверяет, что фраза не мусорная и не слишком длинная."""
    phrase = str(phrase).strip()

    if not phrase:
        return False

    if len(phrase) > max_chars:
        return False

    words = _phrase_words(phrase)

    if not words:
        return False

    if len(words) > max_words:
        return False

    meaningful_words = [
        word for word in words
        if (
            word not in SHAP_PHRASE_STOPWORDS
            or word in SHAP_NEGATION_WORDS
        )
        and not word.isdigit()
    ]

    if not meaningful_words:
        return False

    if len(words) == 1 and len(meaningful_words[0]) < 4:
        return False

    return True


def _split_shap_chunks(tokens, values, max_chunk_tokens=18):
    """
    Делит отзыв на короткие смысловые куски по пунктуации.
    Это нужно, чтобы SHAP не возвращал весь отзыв целиком.
    """
    chunks = []
    current_tokens = []
    current_values = []

    for token, value in zip(tokens, values):
        token_text = _token_to_text(token)

        token_without_punct = re.sub(r"[,.!?;:\n\r]+", " ", token_text)

        if token_without_punct.strip():
            current_tokens.append(token_without_punct)
            current_values.append(float(value))

        has_separator = re.search(r"[,.!?;:\n\r]+", token_text) is not None

        if has_separator and current_tokens:
            chunks.append((current_tokens, current_values))
            current_tokens = []
            current_values = []
            continue

        if len(current_tokens) >= max_chunk_tokens:
            chunks.append((current_tokens, current_values))
            current_tokens = []
            current_values = []

    if current_tokens:
        chunks.append((current_tokens, current_values))

    return chunks


def _best_shap_window(tokens, values, sign=1, max_words=7):
    """
    Находит внутри куска короткое окно с максимальным SHAP-вкладом.

    sign = 1  -> ищем фразы, повышающие вероятность позитивного класса
    sign = -1 -> ищем фразы, понижающие вероятность позитивного класса
    """
    best_phrase = ""
    best_score = 0.0

    n = min(len(tokens), len(values))

    for start in range(n):
        word_count = 0
        value_sum = 0.0
        window_tokens = []

        for end in range(start, n):
            token_text = _token_to_text(tokens[end])
            token_words = _phrase_words(token_text)

            if token_words:
                word_count += len(token_words)

            if word_count > max_words:
                break

            window_tokens.append(token_text)
            value_sum += float(values[end])

            phrase = _tokens_to_phrase(window_tokens)

            if not _is_meaningful_shap_phrase(phrase, max_words=max_words):
                continue

            signed_score = sign * value_sum

            if signed_score <= 0:
                continue

            # Небольшой штраф за слишком длинные фразы,
            # чтобы выбирались именно короткие ключевые фрагменты.
            normalized_score = signed_score / max(word_count, 1) ** 0.35

            if normalized_score > best_score:
                best_score = normalized_score
                best_phrase = phrase

    return best_phrase, best_score


def _extract_shap_phrase_candidates(example, sign=1):
    """
    Из одного SHAP Explanation извлекает короткие фразы,
    а не весь отзыв.
    """
    values = _flatten_shap_values(example.values)
    tokens = list(example.data)

    n = min(len(tokens), len(values))

    if n == 0:
        return []

    tokens = tokens[:n]
    values = values[:n]

    chunks = _split_shap_chunks(tokens, values)
    candidates = []

    for chunk_tokens, chunk_values in chunks:
        phrase, score = _best_shap_window(
            chunk_tokens,
            chunk_values,
            sign=sign,
            max_words=7
        )

        if phrase and score > 0:
            candidates.append((phrase, score))

    return candidates


def _phrase_similarity_key(phrase):
    """Ключ для удаления дублей похожих фраз."""
    words = [
        word for word in _phrase_words(phrase)
        if word not in SHAP_PHRASE_STOPWORDS
    ]

    return " ".join(word[:6] for word in words)


def _are_phrases_similar(phrase_a, phrase_b):
    words_a = set(_phrase_similarity_key(phrase_a).split())
    words_b = set(_phrase_similarity_key(phrase_b).split())

    if not words_a or not words_b:
        return False

    intersection = words_a & words_b
    smaller = min(len(words_a), len(words_b))

    return len(intersection) / max(smaller, 1) >= 0.75


def _rank_unique_shap_phrases(candidates, limit=5):
    """Сортирует SHAP-фразы по силе вклада и убирает повторы."""
    candidates = sorted(candidates, key=lambda item: item[1], reverse=True)

    result = []

    for phrase, score in candidates:
        phrase = str(phrase).strip().lower()
        phrase = re.sub(r"\s+", " ", phrase)
        phrase = phrase.strip(" .,!?:;—-–")

        if not _is_meaningful_shap_phrase(phrase):
            continue

        if any(_are_phrases_similar(phrase, existing) for existing in result):
            continue

        result.append(phrase)

        if len(result) >= limit:
            break

    return result


def fallback_pros_cons_from_reviews(group_df, top_k=5):
    """
    Резервный способ выбора плюсов/минусов, если SHAP недоступен.
    Выбирает более содержательные отзывы.
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
    Извлекает ключевые плюсы и минусы через SHAP.

    Важно:
    - не возвращает отзывы целиком;
    - использует SHAP values на уровне токенов;
    - собирает короткие фразы до 7 слов;
    - плюсы = фразы, повышающие вероятность позитивного класса;
    - минусы = фразы, понижающие вероятность позитивного класса.
    """
    import random

    valid_texts = []

    for text in texts:
        cleaned = normalize_review_point(text, max_len=1000)

        if cleaned:
            valid_texts.append(cleaned)

    if not valid_texts:
        return [], []

    if len(valid_texts) > n_samples:
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

    positive_candidates = []
    negative_candidates = []

    for example in shap_values:
        positive_candidates.extend(
            _extract_shap_phrase_candidates(example, sign=1)
        )

        negative_candidates.extend(
            _extract_shap_phrase_candidates(example, sign=-1)
        )

    pros = _rank_unique_shap_phrases(positive_candidates, limit=top_k)
    cons = _rank_unique_shap_phrases(negative_candidates, limit=top_k)

    return pros, cons

def build_summary_text(product_name, group_df, product_category=""):
    """
    Формирует текстовую аналитику в формате, который понимает блок генерации.
    """
    total = len(group_df)
    positive_count = int((group_df["sentiment"] == 2).sum())
    negative_count = int((group_df["sentiment"] == 1).sum())
    neutral_count = int((group_df["sentiment"] == 0).sum())

    positive_share = round(positive_count / total * 100, 1) if total else 0
    negative_share = round(negative_count / total * 100, 1) if total else 0
    neutral_share = round(neutral_count / total * 100, 1) if total else 0

    pros, cons = pros_cons_from_reviews(
        group_df["review_text"].fillna("").astype(str).tolist(),
        n_samples=min(50, total),
        top_k=5
    )


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


def analyze_uploaded_reviews(
    df,
    detect_ai_reviews=False,
    use_review_reactions=False
):
    """
    Анализирует отзывы BERT-моделью и готовит сводки по товарам.
    Дополнительная оценка качества отзывов включается только по флагам,
    чтобы не замедлять основной анализ.
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
            f"Недостаточно содержательных отзывов для анализа. "
            f"Минимальный порог — {MIN_REVIEWS_FOR_ANALYSIS} отзывов на товар.\n\n"
            f"Удалось собрать и подготовить к анализу:\n{details}\n\n"
            f"Важно: число отзывов на карточке Wildberries и число отзывов, доступных для автоматического анализа, могут отличаться. "
            f"Система учитывает только отзывы с текстом, которые удалось получить и которые прошли фильтр по минимальной длине.\n\n"
            f"Товар не был проанализирован и не сохранён в базу данных."
        )

    prepared_df = prepared_df[
        prepared_df["nm_id"].astype(str).isin(valid_nm_ids)
    ].reset_index(drop=True)

    if detect_ai_reviews or use_review_reactions:
        prepared_df = enrich_reviews_quality(
            prepared_df,
            detect_ai_reviews=detect_ai_reviews,
            use_review_reactions=use_review_reactions
        )

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