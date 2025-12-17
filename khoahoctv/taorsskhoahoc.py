# taorsskhoahoc.py - Scrape KhoaHoc.tv Y học -> Generate RSS (tối ưu tránh trùng, dừng sớm)

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading
import os

# ==================== CONFIG ====================
base_url = "https://khoahoc.tv/yhoc"
num_threads = 15
output_dir = "khoahoctv"
output_file = os.path.join(output_dir, "yhoc_khoahoc_tv.rss")
max_pages = 5000
items_per_full_page = 20
# ===============================================

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

os.makedirs(output_dir, exist_ok=True)

# Đọc RSS cũ để lấy set link đã có (tránh trùng)
existing_links = set()
if os.path.exists(output_file):
    try:
        tree = ET.parse(output_file)
        root = tree.getroot()
        for item in root.findall('.//item'):
            link = item.find('link')
            if link is not None and link.text:
                existing_links.add(link.text.strip())
        print(f"Đọc RSS cũ: Có {len(existing_links)} bài đã tồn tại.")
    except Exception as e:
        print(f"Lỗi đọc RSS cũ: {e}")

# Thread-safe
all_items = []
lock = threading.Lock()
stop_scraping = False  # Signal để dừng tất cả khi gặp trùng

def scrape_page(page_num):
    global stop_scraping
    if stop_scraping:
        return []

    url = f"{base_url}?p={page_num}"
    print(f"[Thread] Bắt đầu trang {page_num}")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        for li in soup.find_all('li', class_='listitem clearfix'):
            if stop_scraping:
                break
            title_a = li.find('a', class_='title')
            if not title_a: continue
            title = title_a.find('h3').text.strip() if title_a.find('h3') else ''
            link_href = title_a.get('href', '')
            link = urljoin(base_url, link_href)
            if not title or not link:
                continue

            # Kiểm tra trùng link
            if link in existing_links:
                print(f"!!! PHÁT HIỆN BÀI TRÙNG (link cũ): {title} -> DỪNG SCRAPE TOÀN BỘ!")
                stop_scraping = True
                return []

            thumb_a = li.find('a', class_='thumb')
            thumb = thumb_a.find('img').get('src') or thumb_a.find('img').get('data-src') or '' if thumb_a and thumb_a.find('img') else ''
            desc = li.find('div', class_='desc').text.strip() if li.find('div', class_='desc') else ''
            
            items.append({'title': title, 'link': link, 'description': desc, 'thumb': thumb})
        
        added = len(items)
        print(f"Trang {page_num}: Hoàn thành ({added} bài mới)")
        return items
    except Exception as e:
        print(f"Lỗi trang {page_num}: {e}")
        return []

# Scrape trang 1 trước (luôn mới nhất)
print("=== Scrape trang 1 ===")
page1_items = scrape_page(1)
with lock:
    all_items.extend(page1_items)

# Scrape song song các trang tiếp nếu chưa dừng
if not stop_scraping:
    print(f"\n=== Scrape song song trang 2 -> {max_pages} ===")
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {executor.submit(scrape_page, p): p for p in range(2, max_pages + 1)}
        for future in as_completed(futures):
            if stop_scraping:
                break
            items = future.result()
            if items:
                with lock:
                    all_items.extend(items)
                print(f"Đã thêm {len(items)} bài mới -> Tổng: {len(all_items)}")

# Tạo RSS mới (chỉ bài mới + cũ, nhưng thực tế all_items chỉ có đến trước trùng)
print("\n=== Tạo RSS mới (ghi đè) ===")
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "Y học - Sức khỏe - KhoaHoc.tv"
ET.SubElement(channel, "link").text = base_url
ET.SubElement(channel, "description").text = "Tin tức y học, sức khỏe mới nhất từ KhoaHoc.tv"

for item_data in all_items:
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = item_data['title']
    ET.SubElement(item, "link").text = item_data['link']
    ET.SubElement(item, "guid", isPermaLink="true").text = item_data['link']
    desc_html = item_data['description']
    if item_data['thumb']:
        desc_html += f'<br/><img src="{item_data["thumb"]}" alt="{item_data["title"]}"/>'
    ET.SubElement(item, "description").text = f"<![CDATA[{desc_html}]]>"

xmlstr = minidom.parseString(ET.tostring(rss, encoding='unicode')).toprettyxml(indent="  ")
with open(output_file, "w", encoding="utf-8") as f:
    f.write(xmlstr)

print(f"\nHOÀN THÀNH! RSS cập nhật tại: {output_file}")
print(f"Tổng bài trong RSS mới: {len(all_items)} (chỉ thêm bài mới nếu có)")
