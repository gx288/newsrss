import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading
import os
import re
from html import unescape
import random
import time

# ==================== CONFIG ====================
base_url = "https://khoahoc.tv/"
num_threads = 8                    # Giảm để tránh bị block
output_dir = "khoahoctv"
output_file = os.path.join(output_dir, "khoahoc_tv.rss")
max_pages = 1011                   # Thay đổi khi test
# ===============================================

# Danh sách User-Agent rotate để tránh bị detect
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
]

headers_base = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Referer": "https://khoahoc.tv/",
    "DNT": "1",
}

os.makedirs(output_dir, exist_ok=True)

# ==================== ĐỌC RSS CŨ ====================
existing_links = set()
old_items = []
if os.path.exists(output_file):
    try:
        old_tree = ET.parse(output_file)
        root = old_tree.getroot()
        for item in root.findall('.//item'):
            link_elem = item.find('link')
            if link_elem is not None and link_elem.text:
                existing_links.add(link_elem.text.strip())
                old_items.append({
                    'title': item.find('title').text or '',
                    'link': link_elem.text.strip(),
                    'description': item.find('description').text or '',
                    'guid': item.find('guid').text or link_elem.text.strip()
                })
        print(f"Đọc RSS cũ: {len(existing_links)} bài đã tồn tại.")
    except Exception as e:
        print(f"Lỗi đọc RSS cũ: {e}")
else:
    print("Không tìm thấy RSS cũ → Tạo mới.")

# Thread-safe
all_new_items = []
lock = threading.Lock()
stop_scraping = False


def get_full_image_url(thumb_url):
    if not thumb_url or 'holder.png' in thumb_url:
        return ''
    return re.sub(r'-(\d+)(?=\.[a-zA-Z]+$)', '', thumb_url)


def scrape_page(page_num):
    global stop_scraping
    if stop_scraping:
        return []

    url = base_url if page_num == 1 else f"{base_url}?p={page_num}"
    print(f"[Thread] Bắt đầu trang {page_num}: {url}")

    # Rotate User-Agent + headers
    headers = headers_base.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"Trang {page_num} lỗi {response.status_code}")
            return []

        # Random delay nhẹ
        time.sleep(random.uniform(0.8, 2.5))

        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        duplicate_count = 0

        for li in soup.find_all('li', class_='listitem clearfix'):
            if stop_scraping:
                break

            title_a = li.find('a', class_='title')
            if not title_a:
                continue

            title_h3 = title_a.find('h3')
            title = (title_h3.text if title_h3 else title_a.text).strip()
            link = urljoin(base_url, title_a.get('href', ''))

            if not title or not link:
                continue

            # === KIỂM TRA TRÙNG ===
            if link in existing_links:
                duplicate_count += 1
                print(f"   [Trang {page_num}] Trùng bài: {title[:60]}...")
                if duplicate_count >= 5:
                    print(f"!!! Trang {page_num} có >=5 bài trùng → DỪNG SCRAPE TOÀN BỘ!")
                    stop_scraping = True
                    return items  # vẫn trả về những bài mới đã crawl được
                continue  # không thêm bài trùng

            # Lấy mô tả
            desc = li.find('div', class_='desc')
            desc_text = desc.text.strip() if desc else ''

            # Lấy ảnh full size
            thumb = ''
            thumb_a = li.find('a', class_='thumb')
            if thumb_a:
                img = thumb_a.find('img')
                if img:
                    src = img.get('data-src') or img.get('src') or ''
                    thumb = get_full_image_url(src)

            items.append({
                'title': title,
                'link': link,
                'description': desc_text,
                'thumb': thumb
            })

        # === LOGIC DỪNG THÔNG MINH ===
        if len(items) == 0 and page_num > 1:
            print(f"Trang {page_num} KHÔNG CÓ BÀI MỚI → DỪNG SCRAPE!")
            stop_scraping = True
        elif duplicate_count >= 5:
            stop_scraping = True

        print(f"Trang {page_num}: Hoàn thành ({len(items)} bài mới | {duplicate_count} trùng)")
        return items

    except Exception as e:
        print(f"Lỗi trang {page_num}: {e}")
        return []


# ==================== CHẠY CRAWL ====================
print("\n=== Bắt đầu crawl trang 1 ===")
page1_items = scrape_page(1)
with lock:
    all_new_items.extend(page1_items)

if not stop_scraping and max_pages > 1:
    print(f"\n=== Crawl song song trang 2 → {max_pages} (8 threads) ===")
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {executor.submit(scrape_page, p): p for p in range(2, max_pages + 1)}
        for future in as_completed(futures):
            if stop_scraping:
                break
            items = future.result()
            if items:
                with lock:
                    all_new_items.extend(items)
                print(f"→ Đã thêm {len(items)} bài mới | Tổng mới: {len(all_new_items)}")

# ==================== TẠO RSS ====================
if not all_new_items and old_items:
    print("\nKHÔNG CÓ BÀI MỚI! Giữ nguyên RSS cũ.")
else:
    print("\n=== ĐANG TẠO RSS MỚI ===")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "KhoaHoc.tv - Tin tức khoa học mới nhất"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = "Cập nhật tin tức khoa học, công nghệ, y học từ KhoaHoc.tv"

    # Bài mới lên trên cùng
    for item_data in all_new_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_data['title']
        ET.SubElement(item, "link").text = item_data['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = item_data['link']

        desc_html = item_data['description']
        if item_data.get('thumb'):
            desc_html += f'<br/><img src="{item_data["thumb"]}" alt="{item_data["title"]}"/>'

        desc_elem = ET.SubElement(item, "description")
        desc_elem.text = f"<![CDATA[{desc_html}]]>"

    # Giữ bài cũ
    for old in old_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = old['title']
        ET.SubElement(item, "link").text = old['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = old['guid']
        clean_desc = unescape(old['description'] or '')
        if not clean_desc.startswith('<![CDATA['):
            clean_desc = f"<![CDATA[{clean_desc}]]>"
        ET.SubElement(item, "description").text = clean_desc

    # Ghi file đẹp
    xmlstr = ET.tostring(rss, encoding='unicode')
    pretty_xml = minidom.parseString(xmlstr).toprettyxml(indent=" ")
    clean_xml = "\n".join(line for line in pretty_xml.splitlines() if line.strip())

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(clean_xml)

    print(f"\nHOÀN THÀNH! RSS được cập nhật tại: {output_file}")
    print(f"Thêm {len(all_new_items)} bài mới | Tổng bài: {len(all_new_items) + len(old_items)}")
