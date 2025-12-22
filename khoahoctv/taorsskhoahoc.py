import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading
import os
import re

# ==================== CONFIG (DỄ THAY ĐỔI) ====================
base_url = "https://khoahoc.tv/yhoc"
num_threads = 15
output_dir = "khoahoctv"
output_file = os.path.join(output_dir, "yhoc_khoahoc_tv.rss")

# THAY ĐỔI ĐỂ TEST NHANH: Chỉ scrape vài trang đầu (ví dụ 5 trang), sau test xong đổi lại lớn hơn
max_pages = 5  # <--- ĐỔI THÀNH 1011 KHI CHẠY THẬT

debug_mode = True  # <--- True để in ra chi tiết thumb của từng bài (debug tại sao holder.png)
# ===============================================

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}
os.makedirs(output_dir, exist_ok=True)

# Đọc RSS cũ (giữ nguyên như trước)
existing_links = set()
old_items = []
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
all_new_items = []
lock = threading.Lock()
stop_scraping = False

def scrape_page(page_num):
    global stop_scraping
    if stop_scraping:
        return []
    url = f"{base_url}?p={page_num}"
    print(f"[Thread] Bắt đầu trang {page_num} - URL: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"   Status code: {response.status_code}")
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

            # ===== DEBUG & LẤY THUMB CHI TIẾT =====
            thumb = ''
            thumb_a = li.find('a', class_='thumb')
            if thumb_a:
                img = thumb_a.find('img')
                if img:
                    # In ra tất cả attributes để debug
                    attrs = dict(img.attrs)
                    if debug_mode:
                        print(f"   DEBUG IMG attrs cho bài '{title}': {attrs}")

                    # Ưu tiên thứ tự: data-src > data-lazy-src > data-original > src > srcset
                    possible_src = (
                        img.get('data-src') or
                        img.get('data-lazy-src') or
                        img.get('data-original') or
                        img.get('src') or
                        ''
                    )

                    if 'srcset' in img.attrs:
                        # srcset thường có nhiều, lấy cái đầu (thường nhỏ) hoặc tìm lớn nhất
                        srcset = img['srcset']
                        if debug_mode:
                            print(f"   DEBUG srcset: {srcset}")
                        # Lấy url đầu tiên
                        possible_src = srcset.split(',')[0].strip().split(' ')[0] or possible_src

                    if possible_src:
                        if 'holder.png' in possible_src:
                            if debug_mode:
                                print(f"   ---> Bỏ qua holder.png cho bài '{title}'")
                        else:
                            # Loại bỏ hậu tố -200, -300, etc.
                            thumb_large = re.sub(r'-(\d+)(?=\.[a-zA-Z]+$)', '', possible_src)
                            thumb = thumb_large if thumb_large != possible_src else possible_src
                            if debug_mode:
                                print(f"   ---> Thumb cuối cùng: {thumb} (từ {possible_src})")
                    else:
                        if debug_mode:
                            print(f"   ---> Không tìm thấy src nào cho bài '{title}'")
                else:
                    if debug_mode:
                        print(f"   ---> Không có <img> trong thumb cho bài '{title}'")
            else:
                if debug_mode:
                    print(f"   ---> Không có <a class='thumb'> cho bài '{title}'")

            items.append({'title': title, 'link': link, 'description': desc_text, 'thumb': thumb})

        print(f"Trang {page_num}: Hoàn thành ({len(items)} bài)")
        return items
    except Exception as e:
        print(f"Lỗi trang {page_num}: {e}")
        return []

# === CHẠY TEST ===
print("=== Scrape trang 1 ===")
page1_items = scrape_page(1)
with lock:
    all_new_items.extend(page1_items)

if not stop_scraping and max_pages > 1:
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
                print(f"Đã thêm {len(items)} bài -> Tổng mới: {len(all_new_items)}")

# In kết quả thumb để kiểm tra
print("\n=== KẾT QUẢ THUMB CÁC BÀI MỚI (DEBUG) ===")
for item in all_new_items[:20]:  # Chỉ in 20 bài đầu
    print(f"{item['title']} -> Thumb: {item['thumb']}")

# Nếu muốn ghi RSS test (tắt debug_mode và chạy thật thì bật phần dưới)
if all_new_items:
    print("\n=== TẠO RSS TEST (chỉ với bài mới) ===")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Y học - Sức khỏe - KhoaHoc.tv (TEST)"
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = "Test debug thumb"

    for item_data in all_new_items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_data['title']
        ET.SubElement(item, "link").text = item_data['link']
        ET.SubElement(item, "guid", isPermaLink="true").text = item_data['link']
        desc_html = item_data['description']
        if item_data.get('thumb'):
            desc_html += f'<br/><img src="{item_data["thumb"]}" alt="{item_data["title"]}"/>'
        ET.SubElement(item, "description").text = f"<![CDATA[{desc_html}]]>"

    xmlstr = minidom.parseString(ET.tostring(rss, encoding='unicode')).toprettyxml(indent="  ")
    test_file = os.path.join(output_dir, "test_debug.rss")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(xmlstr)
    print(f"\nRSS TEST ghi tại: {test_file}")
    print(f"Tổng bài mới: {len(all_new_items)}")
else:
    print("\nKHÔNG CÓ BÀI MỚI")
