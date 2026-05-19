import re
import pandas as pd


GENERIC_PHRASES = [
    "отличный товар",
    "хорошее качество",
    "рекомендую к покупке",
    "всем советую",
    "полностью соответствует описанию",
    "товар понравился",
    "всё супер",
    "всё отлично",
    "спасибо продавцу",
]

AI_STYLE_MARKERS = [
    "данный товар",
    "пользовательский опыт",
    "приобретение оказалось",
    "можно отметить",
    "следует отметить",
    "в целом можно сказать",
    "обладает рядом преимуществ",
    "соотношение цены и качества",
]


def clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


def estimate_generated_review_score(text):
    """
    Оценивает вероятность шаблонности/искусственной генерации отзыва.
    Это не доказательство генерации, а эвристический риск-сигнал.
    """
    if not text:
        return 0

    text = str(text).strip()
    lower_text = text.lower()

    score = 0
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", lower_text)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    word_count = len(words)

    if word_count < 5:
        return 0

    if word_count > 80:
        score += 15

    if len(sentences) >= 4:
        score += 10

    avg_sentence_len = word_count / max(len(sentences), 1)
    if avg_sentence_len > 18:
        score += 10

    generic_hits = sum(1 for phrase in GENERIC_PHRASES if phrase in lower_text)
    ai_hits = sum(1 for phrase in AI_STYLE_MARKERS if phrase in lower_text)

    score += generic_hits * 8
    score += ai_hits * 12

    # Слишком гладкий отзыв без конкретики
    specific_markers = [
        "размер", "цвет", "упаков", "достав", "запах", "текстур", "материал",
        "тон", "кожа", "после", "нанос", "нос", "день", "час", "фото",
        "минус", "плюс", "брала", "купила", "заказала", "пришло"
    ]

    has_specifics = any(marker in lower_text for marker in specific_markers)

    if not has_specifics and word_count > 25:
        score += 20

    # Повторяемость одинаковых слов
    unique_words = set(words)
    unique_ratio = len(unique_words) / max(word_count, 1)

    if unique_ratio < 0.45 and word_count > 30:
        score += 10

    # Чрезмерно рекламный тон
    promo_words = [
        "идеальный", "безупречный", "лучший", "превосходный",
        "великолепный", "незаменимый", "потрясающий"
    ]

    promo_hits = sum(1 for word in promo_words if word in lower_text)
    score += promo_hits * 8

    return clamp(score)


def label_generated_review_risk(score):
    if score >= 65:
        return "высокая шаблонность"
    if score >= 35:
        return "средняя шаблонность"
    return "низкая шаблонность"


def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default

        return int(float(value))
    except Exception:
        return default


def enrich_reviews_quality(
    df,
    detect_ai_reviews=False,
    use_review_reactions=False
):
    """
    Добавляет признаки качества отзывов только по выбранным пользователем режимам.

    detect_ai_reviews=True:
    - считает признаки шаблонности / возможной искусственной генерации текста.

    use_review_reactions=True:
    - учитывает лайки, дизлайки, полезность и ответы продавца, если эти данные есть.
    """
    result = df.copy()

    if "review_text" not in result.columns:
        return result

    if detect_ai_reviews:
        result["ai_suspicion_score"] = result["review_text"].apply(estimate_generated_review_score)
        result["ai_suspicion_label"] = result["ai_suspicion_score"].apply(label_generated_review_risk)

    if use_review_reactions:
        if "helpful_count" not in result.columns:
            result["helpful_count"] = 0

        if "unhelpful_count" not in result.columns:
            result["unhelpful_count"] = 0

        if "answer_text" not in result.columns:
            result["answer_text"] = ""

        result["helpful_count"] = result["helpful_count"].apply(safe_int)
        result["unhelpful_count"] = result["unhelpful_count"].apply(safe_int)
        result["answer_text"] = result["answer_text"].fillna("").astype(str).str.strip()

        result["answer_count"] = result["answer_text"].apply(lambda value: 1 if value else 0)
        result["reaction_score"] = result["helpful_count"] - result["unhelpful_count"]

    return result


def build_review_quality_summary(reviews_df):
    """Формирует сводку по качеству и доверию к отзывам."""
    if reviews_df is None or reviews_df.empty:
        return {
            "total": 0,
            "high_ai_risk_count": 0,
            "high_ai_risk_share": 0,
            "with_reactions_count": 0,
            "with_reactions_share": 0,
            "with_answers_count": 0,
            "with_answers_share": 0,
            "avg_reaction_score": 0,
        }

    total = len(reviews_df)

    high_ai_risk_count = int((reviews_df.get("ai_suspicion_label", "") == "высокая шаблонность").sum())

    helpful = reviews_df.get("helpful_count", pd.Series([0] * total)).fillna(0).astype(int)
    unhelpful = reviews_df.get("unhelpful_count", pd.Series([0] * total)).fillna(0).astype(int)
    answers = reviews_df.get("answer_count", pd.Series([0] * total)).fillna(0).astype(int)
    reaction_score = reviews_df.get("reaction_score", pd.Series([0] * total)).fillna(0).astype(int)

    with_reactions_count = int(((helpful + unhelpful) > 0).sum())
    with_answers_count = int((answers > 0).sum())

    return {
        "total": total,
        "high_ai_risk_count": high_ai_risk_count,
        "high_ai_risk_share": round(high_ai_risk_count / total * 100, 1) if total else 0,
        "with_reactions_count": with_reactions_count,
        "with_reactions_share": round(with_reactions_count / total * 100, 1) if total else 0,
        "with_answers_count": with_answers_count,
        "with_answers_share": round(with_answers_count / total * 100, 1) if total else 0,
        "avg_reaction_score": round(float(reaction_score.mean()), 2) if total else 0,
    }