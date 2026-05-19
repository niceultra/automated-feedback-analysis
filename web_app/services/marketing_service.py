import io
import re
import pandas as pd


def extract_strengths_weaknesses(summary_text):
    """Извлекает сильные и слабые стороны из текстовой аналитики товара."""
    if not summary_text:
        return [], []

    strengths = []
    weaknesses = []

    try:
        strengths_start = summary_text.find("КЛЮЧЕВЫЕ ПЛЮСЫ:")
        weaknesses_start = summary_text.find("КЛЮЧЕВЫЕ МИНУСЫ:")

        if strengths_start != -1 and weaknesses_start != -1:
            strengths_text = summary_text[
                strengths_start + len("КЛЮЧЕВЫЕ ПЛЮСЫ:"):weaknesses_start
            ].strip()

            weaknesses_text = summary_text[
                weaknesses_start + len("КЛЮЧЕВЫЕ МИНУСЫ:"):
            ].strip()

            def parse_points(text):
                points = []

                for line in text.split("\n"):
                    line = line.strip()

                    if line and len(line) > 2 and line[0].isdigit() and (line[1] == "." or line[1] == ")"):
                        point = line[2:].strip().rstrip(".")

                        if point:
                            points.append(point)

                return points

            strengths = parse_points(strengths_text)
            weaknesses = parse_points(weaknesses_text)

    except Exception:
        return [], []

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

    text = str(summary_text)
    text = re.sub(r"\s+", " ", text).strip()

    def to_float(value):
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return 0.0

    total_patterns = [
        r"Всего обработано отзывов:\s*(\d+)",
        r"Всего отзывов:\s*(\d+)",
    ]

    for pattern in total_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            stats["total"] = int(match.group(1))
            break

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


def build_marketing_action_blocks(stats, strengths, weaknesses):
    """Формирует прикладные блоки: карточка, реклама, возражения, доработки."""
    total = stats.get("total", 0)
    positive_share = stats.get("positive_share", 0)
    negative_share = stats.get("negative_share", 0)
    neutral_share = stats.get("neutral_share", 0)

    top_strengths = strengths[:3] if strengths else []
    top_weaknesses = weaknesses[:3] if weaknesses else []

    main_conclusions = []

    if total:
        main_conclusions.append(
            f"Проанализировано {total} отзывов: позитив — {positive_share}%, "
            f"негатив — {negative_share}%, нейтральные — {neutral_share}%."
        )

    if positive_share >= 80:
        main_conclusions.append(
            "У товара выраженный позитивный фон. Его можно продвигать через сильные стороны, подтверждённые отзывами покупателей."
        )
    elif positive_share >= 60:
        main_conclusions.append(
            "Товар в целом воспринимается положительно, но перед активным продвижением важно закрыть повторяющиеся сомнения покупателей."
        )
    else:
        main_conclusions.append(
            "Позитивный фон выражен умеренно. Перед усилением рекламы стоит проверить карточку товара, описание и ожидания покупателей."
        )

    if negative_share >= 15:
        main_conclusions.append(
            "Доля негативных отзывов заметная. Негатив нужно использовать как список возражений для доработки карточки и коммуникации."
        )
    elif negative_share > 0:
        main_conclusions.append(
            "Негатив присутствует, но не доминирует. Его стоит использовать для точечной корректировки описания и рекламных обещаний."
        )
    else:
        main_conclusions.append(
            "Существенный негатив не выделен. Основной акцент можно сделать на преимуществах и сценариях использования товара."
        )

    card_actions = []

    if top_strengths:
        card_actions.append("Вынести в первые экраны карточки товара следующие преимущества:")
        card_actions.extend([f"— {item}" for item in top_strengths])
    else:
        card_actions.append(
            "Явные преимущества выражены слабо. Нужно усилить описание товара через конкретные свойства, сценарии применения и выгоды."
        )

    if top_weaknesses:
        card_actions.append("Добавить в описание уточнения, которые заранее снимают возможные сомнения покупателей.")
        card_actions.append("Проверить, не создаёт ли карточка завышенных ожиданий относительно товара.")

    objection_actions = []

    if top_weaknesses:
        objection_actions.append("Использовать слабые места как основу для FAQ или уточнений в карточке:")
        objection_actions.extend([f"— {item}" for item in top_weaknesses])
        objection_actions.append(
            "Не выносить минусы напрямую в рекламу, а закрывать их через честные и спокойные формулировки."
        )
    else:
        objection_actions.append(
            "Повторяющиеся возражения выражены слабо. Можно сосредоточиться на усилении преимуществ и доверия к товару."
        )

    ad_actions = []

    if top_strengths:
        ad_actions.append("В рекламных заголовках и баннерах использовать формулировки, связанные с реальными плюсами товара.")
        ad_actions.append("Основу рекламного сообщения лучше строить вокруг следующих смыслов:")
        ad_actions.extend([f"— {item}" for item in top_strengths])
    else:
        ad_actions.append(
            "Для рекламы пока не хватает сильных пользовательских инсайтов. Желательно дополнительно изучить отзывы и карточки конкурентов."
        )

    improvement_actions = []

    if negative_share >= 15:
        improvement_actions.append("Провести отдельную проверку причин негативных отзывов.")
        improvement_actions.append("Доработать описание, фото, инфографику или комплектацию, если претензии повторяются.")
    elif top_weaknesses:
        improvement_actions.append("Точечно доработать карточку товара по повторяющимся слабым местам.")
    else:
        improvement_actions.append("Поддерживать текущую коммуникацию и усилить акцент на подтверждённых преимуществах.")

    improvement_actions.append(
        "После изменений повторно собрать отзывы и сравнить динамику тональности."
    )

    return {
        "main_conclusions": main_conclusions,
        "card_actions": card_actions,
        "objection_actions": objection_actions,
        "ad_actions": ad_actions,
        "improvement_actions": improvement_actions,
    }


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