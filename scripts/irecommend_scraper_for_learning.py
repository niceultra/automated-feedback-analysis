# -*- coding: utf-8 -*-
"""
Устойчивый парсер отзывов с iRecommend.ru
Собирает только 5★ (positive_reviews.csv) и 1★ (negative_reviews.csv)
— избегает дублей, делает рандомные паузы, детектирует капчу и перезапускает драйвер.
"""

import re
import time
import csv
import random
import os
from urllib.parse import quote
from bs4 import BeautifulSoup

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

BASE = "https://irecommend.ru"

# ----- CONFIG -----
HEADLESS = False                    # False если хочешь смотреть браузер
RESTART_EVERY_REVIEWS = 200        # перезапуск драйвера каждые N сохранённых отзывов
MAX_POS = 1500
MAX_NEG = 1500
SEARCH_MAX_PRODUCTS = 12           # сколько товаров с одной поисковой страницы брать
SNIPPETS_PER_PRODUCT = 30          # сколько сниппетов взять с карточки
MIN_TEXT_LEN = 60                  # минимальная длина отзыва для записи
SLEEP_BETWEEN_QUERIES = (3.5, 7.5) # диапазон секунд между запросами
SLEEP_BETWEEN_PAGES = (0.8, 1.8)   # паузы между запросами внутри товара
SCROLL_PAUSE = (1.0, 2.2)          # пауза после скролла страницы
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# Путь файлов
POS_PATH = "positive_reviews.csv"
NEG_PATH = "negative_reviews.csv"

# ----- HELPERS -----
def random_user_agent():
    return random.choice(USER_AGENTS)

def random_sleep(rng):
    time.sleep(random.uniform(*rng))

def is_captcha_html(html):
    """Простая проверка: капча-скрипты, фразы, отсутствующие блоки"""
    if not html:
        return True
    low = html.lower()
    indicators = [
        "captcha", "gocaptcha", "доказать что вы человек", "подтвердите", "проверка",
        "cf-chl-bypass", "cloudflare", "captcha-checker"
    ]
    for w in indicators:
        if w in low:
            return True
    return False

def ensure_header(path, writer):
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return
    except Exception:
        pass
    writer.writerow(["id", "category", "text"])

# ----- DRIVER MANAGEMENT -----
def create_driver(headless=HEADLESS, ua=None, proxy=None):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--incognito")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    if ua:
        options.add_argument(f"user-agent={ua}")
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')

    # create driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # small stealth tweaks
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """
        })
    except Exception:
        pass
    return driver

# ----- PARSING UTILITIES -----
def fetch_search_html(driver, query):
    """Загружает страницу поиска через переданный driver и возвращает HTML.
       Позволяет вручную пройти капчу перед парсингом.
    """
    q = quote(query)
    url = f"{BASE}/srch?query={q}"
    try:
        driver.get(url)

        # --- Ручное прохождение капчи ---
        print("Если появится капча, пройдите её вручную в браузере.")
        input("Нажмите Enter, когда страница полностью загрузится и капча пройдена...")
        # -----------------------------------

        # скроллим страницу для подгрузки динамического контента
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/4);")
        random_sleep(SCROLL_PAUSE)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        random_sleep(SCROLL_PAUSE)

        html = driver.page_source
        return html
    except Exception as e:
        print("Ошибка при fetch_search_html:", repr(e))
        return None

def extract_product_links_from_search_html(html, main_word, max_products=SEARCH_MAX_PRODUCTS):
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select("a[href^='/content/']")
    links, seen = [], set()
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        full = BASE + href
        if full in seen:
            continue
        title = a.get_text(strip=True)
        if not title:
            # пробуем взять заголовок в родителе
            p = a.find_parent()
            if p:
                t = p.select_one(".title, div.title, .product-title")
                if t:
                    title = t.get_text(strip=True)
        if not title:
            continue
        if re.search(r"\b" + re.escape(main_word.lower()) + r"\b", title.lower()):
            links.append((title, full))
            seen.add(full)
        if len(links) >= max_products:
            break
    return links

def get_review_snippets_from_product(driver, product_url, max_reviews=SNIPPETS_PER_PRODUCT, wait_seconds=6):
    reviews = []
    seen_links = set()
    try:
        driver.get(product_url)
        # скроллим страницу — отзывы часто подгружаются при прокрутке
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        random_sleep((0.6, 1.2))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        random_sleep((0.8, 2.0))

        # подождём появления хотя бы одного сниппета (если есть)
        try:
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.smTeaser, li.item, div.reviews-list-item"))
            )
        except TimeoutException:
            # продолжаем разбор текущего HTML
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        blocks = soup.select("div.smTeaser, li.item, div.reviews-list-item, div.item, div.smTeaser.woProduct")
        for block in blocks:
            if len(reviews) >= max_reviews:
                break
            # ссылка на полный отзыв
            link_tag = block.select_one("a.reviewTextSnippet, h2.reviewTitle a, a[href^='/content/']")
            link = BASE + link_tag["href"] if link_tag and link_tag.get("href", "").startswith("/") else ""
            if not link:
                continue
            if link in seen_links:
                continue
            seen_links.add(link)

            stars = block.select("div.fivestarWidgetStatic .on")
            rating = len(stars) if stars else None
            if rating and rating in (1, 5):
                reviews.append({"rating": rating, "link": link})
    except WebDriverException as e:
        print("Ошибка get_review_snippets_from_product (WebDriverException):", repr(e))
    except Exception as e:
        print("Ошибка get_review_snippets_from_product:", e)
    return reviews

def get_full_review_text(driver, review_url, wait_seconds=6):
    try:
        driver.get(review_url)
        # прокрутка страницы, чтобы подгрузились все элементы
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        random_sleep((0.6, 1.2))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        random_sleep((0.6, 1.2))

        # ждём появления блока с отзывом
        try:
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.views-field-teaser.reviewText div.description[itemprop='reviewBody']"))
            )
        except TimeoutException:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        review_block = soup.select_one("div.views-field-teaser.reviewText div.description[itemprop='reviewBody']")
        if review_block:
            # получаем текст, заменяя <br> на переносы
            for br in review_block.find_all("br"):
                br.replace_with("\n")
            text = review_block.get_text(" ", strip=True)
            return text

        # fallback: объединяем все <p> на странице
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        if paragraphs:
            return " ".join(paragraphs).strip()

    except WebDriverException as e:
        print("⚠️ WebDriverException в get_full_review_text:", repr(e))
        raise
    except Exception as e:
        print("Ошибка get_full_review_text:", e)
    return ""

# ----- MAIN ----- начать с порошка
def main():
    queries = [
        "samsung","постельное белье", "помада", "крем", "пылесос", "порошок", "наушники", "смартфон",
        "чай", "кофе", "ноутбук", "машина", "дети", "игрушки", "крем для лица", "постельное белье", "одежда"
    ]

    pos_count = 0
    neg_count = 0
    total_processed = 0

    seen_texts_pos = set()
    seen_texts_neg = set()

    # создаём драйвер с рандомным UA
    ua = random_user_agent()
    driver = create_driver(headless=HEADLESS, ua=ua)

    # открываем файлы в append режиме
    pos_file = open(POS_PATH, "a", newline="", encoding="utf-8")
    neg_file = open(NEG_PATH, "a", newline="", encoding="utf-8")
    pos_writer = csv.writer(pos_file)
    neg_writer = csv.writer(neg_file)
    ensure_header(POS_PATH, pos_writer)
    ensure_header(NEG_PATH, neg_writer)

    try:
        for query in queries:
            if pos_count >= MAX_POS and neg_count >= MAX_NEG:
                break

            print(f"\n🔍 Поиск по запросу: {query}")
            # пауза перед поиском
            random_sleep(SLEEP_BETWEEN_QUERIES)

            html = None
            try:
                html = fetch_search_html(driver, query)
            except Exception as e:
                print("Ошибка при fetch_search_html:", e)

            if not html or is_captcha_html(html):
                print("⚠️ Не удалось получить страницу поиска или обнаружена капча для:", query)
                # попытка перезапустить драйвер с новым UA и продолжить
                """try:
                    print("♻️ Перезапускаю драйвер и меняю User-Agent...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    ua = random_user_agent()
                    driver = create_driver(headless=HEADLESS, ua=ua)
                    random_sleep((2.0, 4.0))
                    html = fetch_search_html(driver, query)
                except Exception as e:
                    print("После перезапуска драйвера fetch_search_html всё ещё не работает:", e)
                    print("Рекомендуется сменить IP/VPN и повторить.")
                    continue
"""
            product_links = extract_product_links_from_search_html(html, query, max_products=SEARCH_MAX_PRODUCTS)
            print(f"Найдено товаров: {len(product_links)}")

            for title, url in product_links:
                if pos_count >= MAX_POS and neg_count >= MAX_NEG:
                    break

                print(f"\n🛒 Товар: {title}")
                try:
                    snippets = get_review_snippets_from_product(driver, url, max_reviews=SNIPPETS_PER_PRODUCT)
                except WebDriverException:
                    print("🚨 Драйвер упал при получении сниппетов — перезапускаю...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    ua = random_user_agent()
                    driver = create_driver(headless=HEADLESS, ua=ua)
                    random_sleep((2.0, 4.0))
                    try:
                        snippets = get_review_snippets_from_product(driver, url, max_reviews=SNIPPETS_PER_PRODUCT)
                    except Exception as e:
                        print("После рестарта сниппеты получить не удалось:", e)
                        snippets = []

                if not snippets:
                    print("⚠️ Сниппеты не найдены/ошибка для товара:", title)
                    random_sleep(SLEEP_BETWEEN_PAGES)
                    continue

                for sn in snippets:
                    if pos_count >= MAX_POS and neg_count >= MAX_NEG:
                        break

                    rating = sn.get("rating")
                    link = sn.get("link")
                    if not link or not rating:
                        continue

                    # пауза
                    random_sleep(SLEEP_BETWEEN_PAGES)

                    text = ""
                    try:
                        text = get_full_review_text(driver, link)
                    except WebDriverException:
                        print("🚨 Драйвер упал при загрузке отзыва. Перезапускаю драйвер и пробую ещё раз...")
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        ua = random_user_agent()
                        driver = create_driver(headless=HEADLESS, ua=ua)
                        random_sleep((2.0, 3.5))
                        try:
                            text = get_full_review_text(driver, link)
                        except Exception as e:
                            print("После перезапуска получить отзыв не удалось:", e)
                            text = ""

                    if not text or len(text) < MIN_TEXT_LEN:
                        continue

                    text_clean = " ".join(text.split())

                    # проверка дубликатов
                    if rating == 5:
                        if text_clean in seen_texts_pos:
                            continue
                    elif rating == 1:
                        if text_clean in seen_texts_neg:
                            continue
                    else:
                        continue

                    # записываем в соответствующий файл
                    if rating == 5 and pos_count < MAX_POS:
                        pos_count += 1
                        seen_texts_pos.add(text_clean)
                        pos_writer.writerow([pos_count, query, text_clean])
                        pos_file.flush()
                        total_processed += 1
                        print(f"✅ Положительный отзыв #{pos_count} (всего обработано: {total_processed})")
                    elif rating == 1 and neg_count < MAX_NEG:
                        neg_count += 1
                        seen_texts_neg.add(text_clean)
                        neg_writer.writerow([neg_count, query, text_clean])
                        neg_file.flush()
                        total_processed += 1
                        print(f"❌ Отрицательный отзыв #{neg_count} (всего обработано: {total_processed})")

                    # профилактический перезапуск драйвера
                    if total_processed and total_processed % RESTART_EVERY_REVIEWS == 0:
                        print("♻️ Периодический перезапуск драйвера для очистки памяти и смены отпечатка...")
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        ua = random_user_agent()
                        driver = create_driver(headless=HEADLESS, ua=ua)
                        random_sleep((2.0, 4.0))

                    random_sleep((0.6, 1.6))

                # пауза между товарами
                random_sleep((1.2, 2.6))

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        pos_file.close()
        neg_file.close()
        print(f"\n✅ Завершено. Положительных: {pos_count}, Отрицательных: {neg_count}")

if __name__ == "__main__":
    main()
