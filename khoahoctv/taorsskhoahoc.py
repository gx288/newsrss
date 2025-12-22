import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading
import os
import re  # Thêm import re để xử lý link ảnh lớn

# ==================== CONFIG ====================
base_url = "https://khoahoc.tv/yhoc"
num_threads = 15
output_dir = "khoahoctv"
output_file = os.path.join(output_dir, "yhoc_khoahoc_tv.rss")
max_pages = 1011
items_per_full_page = 20
# ===============================================
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}
os.makedirs(output_dir, exist_ok=True)

# Đọc RSS cũ để lấy set link đã có (tránh trùng) và lưu các items cũ
existing_links = set()
old_items = []  # Lưu danh sách các item cũ dưới dạng dict để dễ prepend
old_tree = None
if os.path.exists(output_file):
    try:
        old_tree = ET.parse(output_file)
        root = old_tree.getroot()
        for item in root.findall('.//item'):
            link_elem = item.find('link')
            if link_elem is not None and link_elem.text:
                link = link_elem.text.strip()
                existing_links.add(link)
                # Lưu item dưới dạng dict để dễ xử lý
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

# Thread-safe
all_new_items = []  # Chỉ lưu các bài mới
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
            if not title_a:
                continue
            title = title_a.find('h3').text.strip() if title_a.find('h3') else title_a.text.strip()
            link_href = title_a.get('href', '')
            link = urljoin(base_url, link_href)
            if not title or not link:
                continue
            # Kiểm tra trùng link
            if link in existing_links:
                print(f"!!! PHÁT HIỆN BÀI TRÙNG (link cũ): {title} -> DỪNG SCRAPE TOÀN BỘ!")
                stop_scraping = True
                return []
            
            desc = li.find('div', class_='desc').text.strip() if li.find('div', class_='desc') else ''
            
            # Xử lý thumb: ưu tiên lấy phiên bản lớn (loại bỏ -200, -300, etc.)
            thumb = ''
            thumb_a = li.find('a', class_='thumb')
            if thumb_a and thumb_a.find('img'):
                img = thumb_a.find('img')
                # Ưu tiên các attribute lazy load phổ biến
                thumb = (img.get('src') or 
                         img.get('data-src') or 
                         img.get('data-lazy-src') or 
                         img.get('data-original') or 
                         img.get('srcset') or '')
                if thumb:
                    # Nếu có srcset, lấy cái đầu tiên (thường là lớn nhất hoặc default)
                    if 'srcset' in thumb.lower():
                        thumb = thumb.split(',')[0].strip().split(' ')[0]
                    # Loại bỏ hậu tố resize như -200, -300, -450, -600 trước phần mở rộng file
                    thumb_large = re.sub(r'-(\d+)(?=\.[a-zA-Z]+$)', '', thumb)
                    # Nếu thay đổi thì dùng phiên bản lớn (thường tồn tại và full size)
                    if thumb_large != thumb:
                        thumb = thumb_large
                    # Nếu thumb là holder.png hoặc rỗng thì bỏ qua
                    if 'holder.png' in thumb or not thumb:
                        thumb = ''

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
    all_new_items.extend(page1_items)

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
                    all_new_items.extend(items)
                print(f"Đã thêm {len(items)} bài mới -> Tổng mới: {len(all_new_items)}")

# Nếu không có bài mới, không cần ghi file
if not all_new_items:
    print("\nKHÔNG CÓ BÀI MỚI! Giữ nguyên RSS cũ.")
else:
    print("\n=== Tạo RSS cập nhật (thêm mới lên đầu) ===")
    # Tạo RSS mới
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Y học - Sức khỏe - KhoaHoc.tv"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = "Tin tức y học, sức khỏe mới nhất từ KhoaHoc.tv"
    
    # Thêm các item mới lên đầu
    for item_data in all_new_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_data['title']
        ET.SubElement(item, "link").text = item_data['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = item_data['link']
        desc_html = item_data['description']
        if item_data.get('thumb'):
            desc_html += f'<br/><img src="{item_data["thumb"]}" alt="{item_data["title"]}"/>'
        ET.SubElement(item, "description").text = f"<![CDATA[{desc_html}]]>"
    
    # Thêm các item cũ sau (giữ nguyên description cũ, kể cả holder.png)
    for old_item_data in old_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = old_item_data['title']
        ET.SubElement(item, "link").text = old_item_data['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = old_item_data['guid']
        ET.SubElement(item, "description").text = old_item_data['description']
    
    # Ghi file đẹp
    xmlstr = minidom.parseString(ET.tostring(rss, encoding='unicode')).toprettyxml(indent="  ")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xmlstr)
    
    print(f"\nHOÀN THÀNH! RSS cập nhật tại: {output_file}")
    print(f"Thêm {len(all_new_items)} bài mới -> Tổng bài trong RSS: {len(all_new_items) + len(old_items)}")
