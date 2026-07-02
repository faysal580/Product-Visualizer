import time
import random
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


INPUT_FILE = "URL for Image.xlsx"
INPUT_COL = "URL"
OUTPUT_FILE = "Image_url.xlsx"
MAX_WORKERS = 5


def setup_driver(headless=True):
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.page_load_strategy = "eager"
    options.add_argument("--window-size=1400,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=en-US,en")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(90)
    return driver


def random_delay(min_sec=1.0, max_sec=3.0):
    time.sleep(random.uniform(min_sec, max_sec))


def read_urls():
    df = pd.read_excel(INPUT_FILE)

    if INPUT_COL not in df.columns:
        raise ValueError(
            f"Column '{INPUT_COL}' not found in {INPUT_FILE}. Found columns: {list(df.columns)}"
        )

    urls = df[INPUT_COL].dropna().astype(str).str.strip().tolist()
    urls = [u for u in urls if u]
    urls = list(dict.fromkeys(urls))  # unique preserve order
    return urls


def clean_image_url(url):
    """
    Example:
    https://img.drz.lazcdn.com/g/kf/xxx.jpg_80x80q80.jpg_.webp
    -> https://img.drz.lazcdn.com/g/kf/xxx.jpg
    """
    if not url:
        return ""

    suffixes = [
        "_80x80q80.jpg_.webp",
        "_400x400q80.jpg_.webp",
        "_2200x2200q80.jpg_.webp",
        "_720x720q80.jpg_.webp",
        "_960x960q80.jpg_.webp",
        "_200x200q80.jpg_.webp",
    ]

    for suffix in suffixes:
        if suffix in url:
            return url.split(suffix)[0]

    return url


def get_all_images(driver):
    image_urls = []

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'next-slick-track')]")
            )
        )
    except Exception:
        return image_urls

    imgs = driver.find_elements(
        By.XPATH,
        "//div[contains(@class,'next-slick-track')]//img[contains(@class,'item-gallery__thumbnail-image')]"
    )

    for img in imgs:
        src = (img.get_attribute("src") or "").strip()
        if src:
            image_urls.append(clean_image_url(src))

    image_urls = list(dict.fromkeys(image_urls))
    return image_urls


def scrape_one_url(url):
    driver = setup_driver(headless=True)

    try:
        random_delay(1.0, 2.5)
        driver.get(url)
        random_delay(1.5, 3.5)

        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        image_urls = get_all_images(driver)

        return {
            "url": url,
            "image url": ", ".join(image_urls),
            "status": "OK" if image_urls else "NO IMAGE FOUND"
        }

    except Exception:
        return {
            "url": url,
            "image url": "",
            "status": "FAILED"
        }

    finally:
        driver.quit()


def main():
    urls = read_urls()
    print(f"Total URLs found: {len(urls)}")

    rows = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(scrape_one_url, url): url for url in urls}

        for future in tqdm(as_completed(future_map), total=len(future_map), desc="Scraping images"):
            rows.append(future.result())

    df = pd.DataFrame(rows, columns=["url", "image url", "status"])
    df.to_excel(OUTPUT_FILE, index=False)

    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()