import uuid
import time
import base64
import requests
from requests.exceptions import RequestException, SSLError, ConnectionError, Timeout


def to_bool(value, default=True):
    """Преобразует строковые значения secrets в bool."""
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in ("1", "true", "yes", "y", "да")


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

        except (SSLError, ConnectionError, Timeout, RequestException) as e:
            last_error = e

            if attempt < max_attempts:
                time.sleep(2 * attempt)
                continue

            raise RuntimeError(str(last_error))

    raise RuntimeError(f"Не удалось выполнить запрос после нескольких попыток: {last_error}")


def build_marketing_prompt(product_name, strengths, weaknesses):
    """Готовит промпт для генерации маркетингового комплекта."""
    return f"""
Ты — профессиональный маркетолог маркетплейсов, специалист по карточкам товаров, рекламе и работе с отзывами покупателей.

Твоя задача — на основе выявленных сильных и слабых сторон товара подготовить материалы для карточки товара и рекламы.
Пиши как маркетолог маркетплейса: понятно, спокойно, конкретно, без украшательства и чрезмерных обещаний.

ТОВАР:
{product_name}

СИЛЬНЫЕ СТОРОНЫ ТОВАРА:
{', '.join(strengths) if strengths else 'Сильные стороны выражены слабо'}

СЛАБЫЕ СТОРОНЫ ИЛИ ВОЗРАЖЕНИЯ:
{', '.join(weaknesses) if weaknesses else 'Существенные слабые стороны не выявлены'}

Сформируй ответ строго по структуре:

1. Заголовки для карточки товара
Дай 5 коротких вариантов заголовков без эмодзи и без символа #.

2. Описание товара
Напиши один готовый текст для описания товара. Текст должен быть спокойным, понятным и без преувеличений.

3. Тезисы для инфографики
Дай 5 коротких пунктов, которые можно вынести на изображения карточки товара.

4. Тексты для рекламы
Дай 3 варианта короткого рекламного текста:
- для баннера;
- для таргетированной рекламы;
- для короткого промопоста.

5. Как закрыть сомнения покупателей
Сформулируй 3 спокойных фразы, которые помогают снять возможные сомнения покупателей.

6. Призывы к действию
Дай 5 вариантов короткого призыва к действию без давления на покупателя.

7. Какие обещания не использовать
Кратко укажи, какие формулировки лучше не использовать в рекламе, чтобы не вызвать недоверие.

Правила:
- Пиши на русском языке.
- Не используй эмодзи.
- Не используй символ # перед заголовками.
- Не используй чрезмерно восторженный рекламный стиль.
- Не используй слова «идеальный», «лучший», «номер один», «безупречный», «гарантированный».
- Не используй слово «отчёт».
- Не упоминай, что текст создан нейросетью.
- Не упоминай, что текст создан на основе отзывов.
- Не выдумывай свойств товара, которых нет в сильных сторонах.
- Не обещай результат, который нельзя проверить.
- Не давай медицинских, лечебных или косметологических обещаний, если они прямо не подтверждены данными.
- Слабые стороны учитывай аккуратно: превращай их в спокойные уточнения, а не в прямое перечисление минусов.
- Пиши конкретно, без абстрактных фраз вроде «высокое качество», если не объяснено, в чём оно проявляется.
- Используй обычный Markdown без декоративных символов.
"""


def generate_marketing_content_with_gigachat(
    product_name,
    strengths,
    weaknesses,
    client_id,
    client_secret,
    scope="GIGACHAT_API_PERS",
    auth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
    api_url="https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
    model="GigaChat",
    verify_ssl=True,
    debug=False,
):
    """Генерирует маркетинговый комплект через GigaChat API."""
    if not client_id or not client_secret:
        return (
            "Ошибка GigaChat: не настроены GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET. "
            "Добавьте их в secrets приложения."
        )

    auth_string = f"{client_id}:{client_secret}"
    base64_string = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {base64_string}",
    }

    payload = {
        "scope": scope
    }

    try:
        response = request_with_retries(
            "POST",
            auth_url,
            headers=headers,
            data=payload,
            verify=verify_ssl,
            timeout=20,
            max_attempts=3
        )

        if response.status_code != 200:
            details = response.text[:500] if debug else "Подробности скрыты. Включите GIGACHAT_DEBUG=true для диагностики."

            return (
                f"Ошибка при получении токена GigaChat: HTTP {response.status_code}.\n\n"
                f"Проверьте GIGACHAT_CLIENT_ID, GIGACHAT_CLIENT_SECRET, GIGACHAT_SCOPE и доступ к API.\n\n"
                f"{details}"
            )

        token_data = response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return (
                "Ошибка GigaChat: токен получен, но в ответе нет access_token. "
                "Проверьте настройки авторизации."
            )

        prompt = build_marketing_prompt(product_name, strengths, weaknesses)

        chat_payload = {
            "model": model,
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
            api_url,
            headers=chat_headers,
            json=chat_payload,
            verify=verify_ssl,
            timeout=90,
            max_attempts=4
        )

        if chat_response.status_code != 200:
            details = chat_response.text[:500] if debug else "Подробности скрыты. Включите GIGACHAT_DEBUG=true для диагностики."

            return (
                f"Ошибка при генерации текста GigaChat: HTTP {chat_response.status_code}.\n\n"
                f"Проверьте модель, доступ к API и лимиты аккаунта.\n\n"
                f"{details}"
            )

        result = chat_response.json()

        try:
            return result["choices"][0]["message"]["content"]
        except Exception:
            details = str(result)[:500] if debug else "Ответ API получен, но его формат отличается от ожидаемого."

            return (
                "Не удалось разобрать ответ GigaChat.\n\n"
                f"{details}"
            )

    except Exception as e:
        error_text = str(e)

        if "CERTIFICATE_VERIFY_FAILED" in error_text or "certificate verify failed" in error_text.lower():
            return (
                "Ошибка SSL при подключении к GigaChat.\n\n"
                "Сервер не смог проверить сертификат API. "
                "Для временной проверки можно добавить в secrets параметр GIGACHAT_VERIFY_SSL=false, "
                "но для нормальной эксплуатации лучше настроить корректные сертификаты."
            )

        if debug:
            return f"Ошибка при обращении к GigaChat: {error_text}"

        return (
            "Не удалось сгенерировать маркетинговый комплект через GigaChat. "
            "Включите GIGACHAT_DEBUG=true в secrets, чтобы увидеть точную причину ошибки."
        )