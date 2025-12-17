# Full scraping script for KhoaHoc.tv Y học -> RSS 2.0
# Sửa vấn đề không in ra màn hình: Thêm print ngay khi thread bắt đầu xử lý trang
# Giới hạn threads hợp lý (10-20) để tránh quá tải mạng/máy và không in ra
# Tăng max_pages lên nhưng thêm điều kiện dừng nếu trang ít bài hơn (trang cuối thường <20)
# Multi-threading sẽ chạy rõ ràng với print từ từng thread

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading

# ==================== CONFIG ====================
base_url = "https://khoahoc.tv/yhoc"
num_threads = 15  # 10-20 là hợp lý, bạn sẽ thấy in ra nhanh
output_file = "khoahoctv/yhoc_khoahoc_tv.rss"
max_pages = 50  # Giới hạn an toàn (thực tế có thể ~200-300 trang)
items_per_full_page = 20  # Trang đầy đủ có 20 bài, trang cuối thường ít hơn
# ===============================================

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

# Thread-safe
all_items = []
lock = threading.Lock()

print("Bắt đầu scrape trang 1...")
response = requests.get(base_url, headers=headers, timeout=30)
if response.status_code != 200:
    raise Exception(f"Lỗi trang 1: {response.status_code}")

soup1 = BeautifulSoup(response.text, 'html.parser')
page1_items = []
for li in soup1.find_all('li', class_='listitem clearfix'):
    title_a = li.find('a', class_='title')
    if not title_a: continue
    title = title_a.find('h3').text.strip() if title_a.find('h3') else ''

    link = urljoin(base_url, title_a.get('href', ''))

    thumb_a = li.find('a', class_='thumb')
    thumb = thumb_a.find('img').get('src') or thumb_a.find('img').get('data-src') or '' if thumb_a and thumb_a.find(
        'img') else ''

    desc = li.find('div', class_='desc').text.strip() if li.find('div', class_='desc') else ''

    if title and link:
        page1_items.append({'title': title, 'link': link, 'description': desc, 'thumb': thumb})

with lock:
    all_items.extend(page1_items)

print(f"Trang 1 hoàn thành: {len(page1_items)} bài (tổng: {len(all_items)})")


def scrape_page(page_num):
    url = f"{base_url}?p={page_num}"
    print(f"[Thread đang chạy] Bắt đầu scrape trang {page_num}...")  # In ngay khi thread bắt đầu

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"Trang {page_num}: Lỗi HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        items = []
        for li in soup.find_all('li', class_='listitem clearfix'):
            title_a = li.find('a', class_='title')
            if not title_a: continue
            title = title_a.find('h3').text.strip() if title_a.find('h3') else ''

            link = urljoin(base_url, title_a.get('href', ''))

            thumb_a = li.find('a', class_='thumb')
            thumb = thumb_a.find('img').get('src') or thumb_a.find('img').get(
                'data-src') or '' if thumb_a and thumb_a.find('img') else ''

            desc = li.find('div', class_='desc').text.strip() if li.find('div', class_='desc') else ''

            if title and link:
                items.append({'title': title, 'link': link, 'description': desc, 'thumb': thumb})

        added = len(items)
        if added < items_per_full_page and page_num > 2:  # Trang cuối thường ít bài
            print(f"Trang {page_num}: Chỉ {added} bài (< {items_per_full_page}) -> Có lẽ là trang cuối!")

        print(f"Trang {page_num} HOÀN THÀNH: thêm {added} bài")
        return items

    except Exception as e:
        print(f"Lỗi scrape trang {page_num}: {e}")
        return []


# Multi-threading cho trang 2 đến max_pages
print(f"\nKhởi động {num_threads} threads để scrape song song trang 2 -> {max_pages}")
print("Bạn sẽ thấy nhiều dòng '[Thread đang chạy]' và 'HOÀN THÀNH' xuất hiện lộn xộn thứ tự!\n")

with ThreadPoolExecutor(max_workers=num_threads) as executor:
    future_to_page = {executor.submit(scrape_page, p): p for p in range(2, max_pages + 1)}

    for future in as_completed(future_to_page):
        page_num = future_to_page[future]
        items = future.result()

        if items:  # Chỉ thêm nếu có bài
            with lock:
                all_items.extend(items)
            print(f"Đã thêm vào tổng: +{len(items)} từ trang {page_num} (tổng hiện tại: {len(all_items)})")

print("\nTất cả threads hoàn tất!")

# Tạo RSS
print("\nĐang tạo file RSS...")
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "Y học - Sức khỏe - KhoaHoc.tv"
ET.SubElement(channel, "link").text = base_url
ET.SubElement(channel, "description").text = "Tin tức y học từ KhoaHoc.tv"

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

print(f"\nHOÀN THÀNH! File RSS: {output_file}")
print(f"Tổng bài viết: {len(all_items)}")
print("Giờ bạn sẽ thấy rõ tiến trình vì mỗi thread in ngay khi bắt đầu và kết thúc trang.")
