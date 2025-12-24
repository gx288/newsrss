# SKDS/taorsstheolink/scrape_ungthu_rss.py
# Scraper chuyên mục Ung thư → tạo RSS feed
# ĐÃ FIX LỖI TIMEOUT TRÊN GITHUB ACTIONS

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementClickInterceptedException, WebDriverException
)
import time
from datetime import datetime
import os
import xml.etree.ElementTree as ET
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException, ElementClickInterceptedException
)

# ====================== CẤU HÌNH ======================
BASE_URL = "https://suckhoedoisong.vn/y-hoc-360/ung-thu.htm"
RSS_OUTPUT_PATH = "../ung_thu_rss.xml"          # Output ở thư mục SKDS gốc
MAX_ITEMS = 100                                # Tối đa bài trong RSS
DUPLICATE_THRESHOLD = 10                       # Gặp 10 bài trùng liên tiếp → dừng
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
    if not os.path.exists(RSS_OUTPUT_PATH):
        print("Chưa có RSS cũ → tạo mới hoàn toàn.")
        return set()
    
    try:
        tree = ET.parse(RSS_OUTPUT_PATH)
        root = tree.getroot()
        links = {item.findtext("link", "").strip().replace("<![CDATA[", "").replace("]]>", "") 
                 for item in root.findall(".//item") if item.findtext("link")}
        print(f"Đã load {len(links)} link từ RSS cũ.")
        return links
    except Exception as e:
        print(f"Lỗi đọc RSS cũ: {e}")
        return set()


def create_driver():
    print("=== KHỞI TẠO UNDETECTED CHROME DRIVER ===")
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    # Tắt ảnh để nhanh hơn (giữ JS để load thêm bài)
    options.add_argument("--blink-settings=imagesEnabled=false")

    # undetected-chromedriver tự xử lý headless + stealth
    driver = uc.Chrome(options=options, use_subprocess=True)
    driver.set_page_load_timeout(90)
    return driver


def scrape_page():
    driver = create_driver()
    
    # Retry driver.get() tối đa 2 lần
    for attempt in range(2):
        try:
            print(f"Mở trang (lần {attempt + 1}): {BASE_URL}")
            driver.get(BASE_URL)
            break  # Thành công → thoát vòng lặp
        except Exception as e:
            print(f"Lỗi load trang lần {attempt + 1}: {e}")
            if attempt == 1:
                print("Đã thử 2 lần → bỏ cuộc.")
                driver.quit()
                return []
            print("Đóng driver cũ và thử lại với driver mới...")
            driver.quit()
            driver = create_driver()
            time.sleep(5)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "box-category-item"))
        )
        print("Trang đã load thành công bài viết đầu tiên.")
    except TimeoutException:
        print("Timeout chờ bài viết → dừng scrape.")
        driver.quit()
        return []

    existing_links = load_existing_links()
    new_items = []
    duplicate_streak = 0

    # Load thêm bằng nút "HIỂN THỊ THÊM BÀI"
    while len(new_items) < MAX_ITEMS:
        current_count = len(driver.find_elements(By.CLASS_NAME, "box-category-item"))
        print(f"Hiện có {current_count} bài hiển thị.")

        try:
            more_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.list__viewmore"))
            )
            print("Tìm thấy nút 'HIỂN THỊ THÊM BÀI' → click...")
            try:
                more_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", more_button)
            time.sleep(5)
        except (NoSuchElementException, TimeoutException):
            print("Không còn nút Xem thêm → đã load hết.")
            break

    # Trích xuất bài viết
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

        # Kiểm tra trùng
        if link in existing_links or any(it['link'] == link for it in new_items):
            duplicate_streak += 1
            print(f"[{idx+1}] TRÙNG (streak: {duplicate_streak}) → bỏ qua: {title}")
            if duplicate_streak >= DUPLICATE_THRESHOLD:
                print(f"Đã gặp {DUPLICATE_THRESHOLD} bài trùng liên tiếp → dừng.")
                break
            continue
        else:
            duplicate_streak = 0

        # Lấy ảnh, thời gian, sapo
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
        print(f"[{idx+1}] MỚI → {title}")

        if len(new_items) >= MAX_ITEMS:
            print(f"Đã đủ {MAX_ITEMS} bài mới → dừng.")
            break

    driver.quit()
    print(f"\n=== HOÀN TẤT: Lấy được {len(new_items)} bài MỚI ===")
    return new_items


if __name__ == "__main__":
    print("=== BẮT ĐẦU CẬP NHẬT RSS UNG THƯ ===\n")
    new_items = scrape_page()

    # Load bài cũ
    old_items = []
    if os.path.exists(RSS_OUTPUT_PATH):
        try:
            tree = ET.parse(RSS_OUTPUT_PATH)
            root = tree.getroot()
            for item_elem in root.findall(".//item"):
                old_items.append({
                    'title': (item_elem.findtext("title") or "").replace("<![CDATA[", "").replace("]]>", "").strip(),
                    'sapo': (item_elem.findtext("description") or "").replace("<![CDATA[", "").replace("]]>", "").strip(),
                    'link': (item_elem.findtext("link") or "").replace("<![CDATA[", "").replace("]]>", "").strip(),
                    'img': item_elem.find("enclosure").get("url") if item_elem.find("enclosure") is not None else "",
                    'pubdate': item_elem.findtext("pubDate") or ""
                })
            print(f"Đã load {len(old_items)} bài cũ.")
        except Exception as e:
            print(f"Lỗi parse RSS cũ: {e}")

    # Ghép: mới + cũ
    all_items = new_items + old_items
    if len(all_items) > MAX_ITEMS:
        all_items = all_items[:MAX_ITEMS]
        print(f"Giữ lại {MAX_ITEMS} bài mới nhất.")

    # Ghi RSS mới
    rss_content = generate_rss(all_items)
    os.makedirs(os.path.dirname(RSS_OUTPUT_PATH) or '.', exist_ok=True)
    with open(RSS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(rss_content)

    print(f"\nĐÃ CẬP NHẬT RSS THÀNH CÔNG: {RSS_OUTPUT_PATH}")
    print(f"Tổng: {len(all_items)} bài ({len(new_items)} mới + {len(old_items)} cũ)")
    print("\n=== KẾT THÚC ===")
