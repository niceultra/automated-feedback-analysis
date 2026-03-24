import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


def scroll_page(driver, scroll_count=5):
    for _ in range(scroll_count):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)


def parse_reviews(html):
    soup = BeautifulSoup(html, "html.parser")
    reviews = []

    items = soup.find_all("li", class_="comments__item")

    for item in items:
        try:
            author = item.find("p", class_="feedback__header").text.strip()
            text = item.find("p", class_="feedback__text").text.strip()
            date = item.find("div", class_="feedback__date").text.strip()

            rating_span = item.find("span", class_="feedback__rating")
            rating_class = rating_span.get("class")

            # WB кодирует рейтинг в starX
            rating = None
            for cls in rating_class:
                if "star" in cls:
                    rating = cls.replace("star", "")

            reviews.append({
                "author": author,
                "text": text,
                "date": date,
                "rating": rating
            })
        except:
            continue

    return reviews


def get_wb_reviews(url, scrolls=5):
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    driver.get(url)

    wait = WebDriverWait(driver, 20)

    # Ждём появления блока отзывов
    wait.until(EC.presence_of_element_located(
        (By.CLASS_NAME, "comments__item")
    ))

    scroll_page(driver, scroll_count=scrolls)

    html = driver.page_source
    driver.quit()

    return parse_reviews(html)


# 🔎 Пример товара
url = "https://www.wildberries.ru/catalog/402596368/feedbacks?imtId=436938606&size=580516577"

reviews = get_wb_reviews(url, scrolls=7)

print(f"Найдено отзывов: {len(reviews)}")

# сохраняем
with open("../../../wb_reviews.json", "w", encoding="utf-8") as f:
    json.dump(reviews, f, ensure_ascii=False, indent=4)