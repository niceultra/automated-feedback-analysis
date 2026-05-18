import uuid
import time
import base64
import requests
from requests.exceptions import SSLError, ConnectionError, Timeout


def request_with_retries(method, url, max_attempts=4, timeout=60, **kwargs):
    """Выполняет HTTP-запрос с повторными попытками."""
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                timeout=timeout,
                **kwargs
            )

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


def build_marketing_prompt(product_name, strengths, weaknesses):
    """Готовит промпт для генерации маркетингового комплекта."""
    return f"""
Ты — профессиональный маркетолог маркетплейсов, специалист по карточкам товаров, рекламе и работе с отзывами покупателей.

Твоя задача — на основе выявленных сильных и слабых сторон товара подготовить готовый маркетинговый комплект.
Пиши так, чтобы результат можно было сразу использовать в работе маркетолога.

ТОВАР:
{product_name}

СИЛЬНЫЕ СТОРОНЫ ТОВАРА:
{', '.join(strengths) if strengths else 'Сильные стороны выражены слабо'}

СЛАБЫЕ СТОРОНЫ ИЛИ ВОЗРАЖЕНИЯ:
{', '.join(weaknesses) if weaknesses else 'Существенные слабые стороны не выявлены'}

Сформируй ответ строго по структуре:

1. Заголовки для карточки товара
Дай 5 коротких вариантов заголовков.

2. Текст для описания товара
Напиши один готовый текст для описания товара.

3. Преимущества для инфографики
Дай 5 коротких пунктов, которые можно вынести на изображения карточки товара.

4. Рекламные объявления
Дай 3 варианта короткого рекламного текста:
- для баннера;
- для таргетированной рекламы;
- для короткого промопоста.

5. Работа с возражениями
Сформулируй 3 спокойных фразы, которые помогают закрыть возможные сомнения покупателей.

6. CTA
Дай 5 вариантов призыва к действию.

7. Что не стоит обещать
Кратко укажи, какие обещания лучше не использовать в рекламе.

Правила:
- Пиши на русском языке.
- Не используй слово «отчёт».
- Не упоминай, что текст создан нейросетью.
- Не упоминай, что текст создан на основе отзывов.
- Не выдумывай свойств товара, которых нет в сильных сторонах.
- Не обещай гарантированный результат.
- Не используй агрессивные формулировки вроде «лучший», «идеальный», «номер один», если это не подтверждено данными.
- Слабые стороны учитывай аккуратно.
- Пиши конкретно, без абстрактных фраз.
- Используй Markdown для удобного отображения.
"""


def generate_marketing_content_with_gigachat(
    product_name,
    strengths,
    weaknesses,
    client_id,
    client_secret,
):
    """Генерирует маркетинговый комплект через GigaChat API."""
    if not client_id or not client_secret:
        return (
            "Ошибка: не настроены GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET. "
            "Добавьте их в secrets приложения."
        )

    auth_string = f"{client_id}:{client_secret}"
    base64_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {base64_string}",
    }

    payload = {
        "scope": "GIGACHAT_API_PERS"
    }

    try:
        response = request_with_retries(
            "POST",
            token_url,
            headers=headers,
            data=payload,
            timeout=20,
            max_attempts=3
        )

        if response.status_code != 200:
            return (
                f"Ошибка при получении токена GigaChat ({response.status_code}). "
                f"Проверьте GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET и доступ к API."
            )

        access_token = response.json().get("access_token")
        if not access_token:
            return "Не удалось получить access_token от GigaChat."

        prompt = build_marketing_prompt(product_name, strengths, weaknesses)

        chat_payload = {
            "model": "GigaChat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.55,
            "max_tokens": 1600
        }

        chat_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        chat_response = request_with_retries(
            "POST",
            chat_url,
            headers=chat_headers,
            json=chat_payload,
            timeout=90,
            max_attempts=4
        )

        chat_response.raise_for_status()
        result = chat_response.json()

        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]

        return "Не удалось получить корректный ответ от GigaChat. Попробуйте повторить генерацию позже."

    except Exception:
        return (
            "Не удалось сгенерировать маркетинговый комплект через GigaChat. "
            "Проверьте настройки API, подключение к интернету и повторите попытку."
        )