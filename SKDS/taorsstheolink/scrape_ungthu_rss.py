# SKDS/taorsstheolink/scrape_ungthu_rss.py
# Scrape chuyên mục Ung thư → tạo RSS
# Chạy trên GitHub Actions

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementClickInterceptedException
)
import time
from datetime import datetime
import os
import xml.etree.ElementTree as ET

# ====================== CẤU HÌNH ======================
BASE_URL = "https://suckhoedoisong.vn/y-hoc-360/ung-thu.htm"
RSS_OUTPUT_PATH = "../ung_thu_rss.xml"  # Thư mục gốc SKDS
MAX_ITEMS = 100          # Tối đa bao nhiêu bài trong RSS (tăng lên nếu muốn)
DUPLICATE_THRESHOLD = 10 # Nếu gặp 10 bài liên tiếp trùng → dừng load thêm
# =====================================================

def generate_rss(items):
    now = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0700")
    
    rss = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title><![CDATA[ Ung thư - Sức khỏe & Đời sống ]]></title>
<description><![CDATA[ Tin tức mới nhất về ung thư từ suckhoedoisong.vn ]]></description>
<link><![CDATA[ {BASE_URL} ]]></link>
<language>vi-vn</language>
<copyright>suckhoedoisong.vn</copyright>
<lastBuildDate>{now}</lastBuildDate>
<docs>https://suckhoedoisong.vn</docs>
<generator>GitHub Action Scraper</generator>
<ttl>50</ttl>\n'''
    
    for item in items:
        rss += f'''<item>
<title><![CDATA[ {item['title']} ]]></title>
<description><![CDATA[ {item['sapo']} ]]></description>
<link><![CDATA[ {item['link']} ]]></link>
<enclosure url="{item['img']}" length="0" type="image/jpeg"/>
<pubDate>{item['pubdate']}</pubDate>
</item>\n'''
    
    rss += '''</channel>
</rss>'''
    return rss


def load_existing_links():
    """Đọc các link đã có trong RSS cũ để kiểm tra trùng"""
    if not os.path.exists(RSS_OUTPUT_PATH):
        return set()
    
    try:
        tree = ET.parse(RSS_OUTPUT_PATH)
        root = tree.getroot()
        links = set()
        for item in root.findall(".//item/link"):
            text = item.text
            if text:
                links.add(text.strip())
        print(f"Đã load {len(links)} link cũ từ RSS hiện tại.")
        return links
    except Exception as e:
        print(f"Lỗi đọc RSS cũ: {e}")
        return set()


def scrape_page():
    print("=== KHỞI ĐỘNG SELENIUM ===")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    
    driver = webdriver.Chrome(options=options)
    driver.get(BASE_URL)
    
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, "box-category-item"))
    )
    print("Trang đã load xong.")

    existing_links = load_existing_links()
    new_items = []
    duplicate_streak = 0  # Đếm số bài trùng liên tiếp

    while True:
        print(f"Hiện tại có {len(driver.find_elements(By.CLASS_NAME, 'box-category-item'))} bài trên trang.")

        try:
            more_button = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.list__viewmore"))
            )
            print("Click nút 'HIỂN THỊ THÊM BÀI'...")
            try:
                more_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", more_button)
            time.sleep(4)

            # Reset streak nếu có bài mới (không kiểm tra ngay, sẽ kiểm tra ở phần extract)
        except (NoSuchElementException, TimeoutException):
            print("Không còn nút Xem thêm → đã load hết.")
            break

        if len(new_items) >= MAX_ITEMS:
            print(f"Đã đạt giới hạn {MAX_ITEMS} bài mới → dừng.")
            break

    print("\n=== BẮT ĐẦU TRÍCH XUẤT BÀI VIẾT ===")
    item_elements = driver.find_elements(By.CLASS_NAME, "box-category-item")

    for idx, elem in enumerate(item_elements):
        try:
            title_elem = elem.find_element(By.CSS_SELECTOR, "h3 a.box-category-link-title")
            title = title_elem.text.strip()
            link = title_elem.get_attribute("href")
            if not link.startswith("http"):
                link = "https://suckhoedoisong.vn" + link
        except:
            continue

        # Kiểm tra trùng lặp
        if link in existing_links or any(item['link'] == link for item in new_items):
            duplicate_streak += 1
            print(f"[{idx+1}] Bài trùng (streak: {duplicate_streak}) → bỏ qua: {title}")
            if duplicate_streak >= DUPLICATE_THRESHOLD:
                print(f"Đã gặp {DUPLICATE_THRESHOLD} bài trùng liên tiếp → dừng scrape.")
                break
            continue
        else:
            duplicate_streak = 0  # reset nếu có bài mới

        try:
            img = elem.find_element(By.CSS_SELECTOR, "img.box-category-avatar").get_attribute("src")
        except:
            img = "https://suckhoedoisong.vn/assets/images/logo-skds.png"

        try:
            time_str = elem.find_element(By.CSS_SELECTOR, "span.box-category-time").get_attribute("title")
            dt = datetime.strptime(time_str, "%d/%m/%Y %H:%M")
            pubdate = dt.strftime("%a, %d %b %Y %H:%M:%S +0700")
        except:
            pubdate = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0700")

        try:
            sapo = elem.find_element(By.CLASS_NAME, "box-category-sapo").text.strip()
            if not sapo.startswith("SKĐS"):
                sapo = "SKĐS - " + sapo
        except NoSuchElementException:
            sapo = f"SKĐS - {title}"

        new_items.append({
            'title': title,
            'sapo': sapo,
            'link': link,
            'img': img,
            'pubdate': pubdate
        })
        print(f"[{idx+1}] NEW → {title}")

        if len(new_items) >= MAX_ITEMS:
            print(f"Đã đủ {MAX_ITEMS} bài mới → dừng.")
            break

    driver.quit()
    print(f"\n=== HOÀN TẤT: Thu thập được {len(new_items)} bài MỚI ===")
    return new_items


if __name__ == "__main__":
    new_items = scrape_page()

    # Đọc RSS cũ (nếu có) và thêm bài mới vào ĐẦU danh sách
    old_items = []
    if os.path.exists(RSS_OUTPUT_PATH):
        try:
            tree = ET.parse(RSS_OUTPUT_PATH)
            root = tree.getroot()
            for item_elem in root.findall(".//item"):
                title = item_elem.find("title").text or ""
                desc = item_elem.find("description").text or ""
                link = item_elem.find("link").text or ""
                img = item_elem.find("enclosure").get("url") if item_elem.find("enclosure") is not None else ""
                pubdate = item_elem.find("pubDate").text or ""
                old_items.append({'title': title, 'sapo': desc, 'link': link, 'img': img, 'pubdate': pubdate})
            print(f"Đã load {len(old_items)} bài cũ từ RSS.")
        except Exception as e:
            print(f"Lỗi parse RSS cũ: {e}")

    # Ghép: bài mới + bài cũ (bài mới nằm trên)
    all_items = new_items + old_items

    # Giới hạn tổng số bài nếu cần
    if len(all_items) > MAX_ITEMS:
        all_items = all_items[:MAX_ITEMS]
        print(f"Chỉ giữ lại {MAX_ITEMS} bài mới nhất.")

    # Tạo RSS mới
    rss_content = generate_rss(all_items)

    # Ghi file ở thư mục cha
    os.makedirs(os.path.dirname(RSS_OUTPUT_PATH) or '.', exist_ok=True)
    with open(RSS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(rss_content)

    print(f"Đã cập nhật RSS: {RSS_OUTPUT_PATH} (tổng {len(all_items)} bài)")
