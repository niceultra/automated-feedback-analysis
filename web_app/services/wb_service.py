import re
import gzip
import json
import time
import pandas as pd
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
    """Возвращает список basket-хостов Wildberries."""
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
    """Формирует ссылку на карточку товара Wildberries."""
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
    """Приводит один отзыв Wildberries к формату приложения."""
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


def fetch_wb_reviews_dataframe(
    products: list[str],
    limit: int = 0,
    min_text_length: int = 20
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
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
            row = flatten_wb_feedback_for_app(
                item,
                product_info,
                min_text_length=min_text_length
            )

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

    df = pd.DataFrame(
        all_rows,
        columns=["nmId", "product_name", "category_name", "product_url", "rating", "text"]
    )

    return df, fetch_report