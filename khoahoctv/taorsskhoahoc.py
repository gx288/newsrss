import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading
import os
import re
from html import unescape  # Để xử lý description cũ bị escape

# ==================== CONFIG ====================
base_url = "https://khoahoc.tv/yhoc"
num_threads = 15
output_dir = "khoahoctv"
output_file = os.path.join(output_dir, "yhoc_khoahoc_tv.rss")
max_pages = 1011  # Thay đổi nếu muốn test ít trang hơn
# ===============================================
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}
os.makedirs(output_dir, exist_ok=True)

# Đọc RSS cũ
existing_links = set()
old_items = []
if os.path.exists(output_file):
    try:
        old_tree = ET.parse(output_file)
        root = old_tree.getroot()
        for item in root.findall('.//item'):
            link_elem = item.find('link')
            if link_elem is not None and link_elem.text:
                link = link_elem.text.strip()
                existing_links.add(link)
                title = item.find('title').text if item.find('title') is not None else ''
                description = item.find('description').text if item.find('description') is not None else ''
                guid = item.find('guid').text if item.find('guid') is not None else link
                old_items.append({
                    'title': title,
                    'link': link,
                    'description': description,
                    'guid': guid
                })
        print(f"Đọc RSS cũ: Có {len(existing_links)} bài đã tồn tại.")
    except Exception as e:
        print(f"Lỗi đọc RSS cũ: {e}")
else:
    print("Không tìm thấy RSS cũ -> Tạo mới hoàn toàn.")

# Thread-safe
all_new_items = []
lock = threading.Lock()
stop_scraping = False

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
            if not title_a:
                continue
            title_h3 = title_a.find('h3')
            title = title_h3.text.strip() if title_h3 else title_a.text.strip()
            link_href = title_a.get('href', '')
            link = urljoin(base_url, link_href)
            if not title or not link:
                continue

            if link in existing_links:
                print(f"!!! PHÁT HIỆN BÀI TRÙNG: {title} -> DỪNG SCRAPE!")
                stop_scraping = True
                return []

            desc = li.find('div', class_='desc')
            desc_text = desc.text.strip() if desc else ''

            # Lấy thumb: ưu tiên data-src (lazy load), fallback src
            thumb = ''
            thumb_a = li.find('a', class_='thumb')
            if thumb_a:
                img = thumb_a.find('img')
                if img:
                    possible_src = img.get('data-src') or img.get('src') or ''
                    if possible_src and 'holder.png' not in possible_src:
                        # Loại bỏ hậu tố -200, -300, etc. để lấy full size
                        thumb_large = re.sub(r'-(\d+)(?=\.[a-zA-Z]+$)', '', possible_src)
                        thumb = thumb_large if thumb_large != possible_src else possible_src

            items.append({'title': title, 'link': link, 'description': desc_text, 'thumb': thumb})

        print(f"Trang {page_num}: Hoàn thành ({len(items)} bài mới)")
        return items
    except Exception as e:
        print(f"Lỗi trang {page_num}: {e}")
        return []

# Scrape trang 1 trước
print("=== Scrape trang 1 ===")
page1_items = scrape_page(1)
with lock:
    all_new_items.extend(page1_items)

# Scrape song song
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
                    all_new_items.extend(items)
                print(f"Đã thêm {len(items)} bài mới -> Tổng mới: {len(all_new_items)}")

# Tạo RSS
if not all_new_items and old_items:
    print("\nKHÔNG CÓ BÀI MỚI! Giữ nguyên RSS cũ.")
else:
    print("\n=== TẠO RSS MỚI ===")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Y học - Sức khỏe - KhoaHoc.tv"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = "Tin tức y học, sức khỏe mới nhất từ KhoaHoc.tv"

    # Bài mới lên đầu (ảnh full size đẹp)
    for item_data in all_new_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_data['title']
        ET.SubElement(item, "link").text = item_data['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = item_data['link']
        
        desc_html = item_data['description']
        if item_data.get('thumb'):
            desc_html += f'<br/><img src="{item_data["thumb"]}" alt="{item_data["title"]}"/>'
        
        # Gán thẳng CDATA vào .text → ElementTree sẽ giữ nguyên không escape
        description_elem = ET.SubElement(item, "description")
        description_elem.text = f"<![CDATA[{desc_html}]]>"

    # Bài cũ (giữ nguyên hoặc sửa nếu bị escape trước đó)
    for old_item_data in old_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = old_item_data['title']
        ET.SubElement(item, "link").text = old_item_data['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = old_item_data['guid']
        
        # Unescape description cũ (nếu bị &lt; &gt; &quot;)
        clean_desc = unescape(old_item_data['description'] or '')
        
        # Nếu chưa có CDATA thì thêm vào
        if not clean_desc.strip().startswith('<![CDATA['):
            clean_desc = f"<![CDATA[{clean_desc.strip()}]]>"
        
        desc_elem = ET.SubElement(item, "description")
        desc_elem.text = clean_desc

    # Ghi file đẹp
    xmlstr = ET.tostring(rss, encoding='unicode', method='xml')
    reparsed = minidom.parseString(xmlstr)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    # Xóa các dòng trống thừa do toprettyxml tạo ra
    lines = [line for line in pretty_xml.splitlines() if line.strip()]
    xmlstr_clean = "\n".join(lines)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xmlstr_clean)

    print(f"\nHOÀN THÀNH! RSS đã được tạo/cập nhật tại: {output_file}")
    print(f"Thêm {len(all_new_items)} bài mới -> Tổng bài trong RSS: {len(all_new_items) + len(old_items)}")
