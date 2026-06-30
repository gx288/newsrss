import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from xml.dom import minidom
from urllib.parse import urljoin
import threading
import os
import re
import time
import random
from datetime import datetime
from html import unescape

import gspread
from google.oauth2.service_account import Credentials

# ==================== CONFIG ====================
base_url = "https://khoahoc.tv/"
num_threads = 8
output_dir = "khoahoctv"
output_file = os.path.join(output_dir, "rsstrangchu.rss")
max_pages_input = os.getenv('MAX_PAGES', '1011')
if max_pages_input.lower() in ['all', '0', '']:
    max_pages = 200000
else:
    max_pages = int(max_pages_input)

# Google Sheet
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'
SPREADSHEET_ID = '14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo'
SHEET_NAME = 'Khoahoc_TV_Full'          # Sheet sẽ tự tạo nếu chưa có
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

headers_base = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Referer": "https://khoahoc.tv/",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

# Tạo credentials Google Sheet
if os.getenv('GOOGLE_SHEETS_CREDENTIALS'):
    os.makedirs('khoahoctv', exist_ok=True)
    with open(SERVICE_ACCOUNT_FILE, 'w', encoding='utf-8') as f:
        f.write(os.getenv('GOOGLE_SHEETS_CREDENTIALS'))

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

# Mở hoặc tạo worksheet
try:
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    sheet = client.open_by_key(SPREADSHEET_ID).add_worksheet(title=SHEET_NAME, rows=1000, cols=10)
    sheet.append_row(["Title", "Date", "Link", "Image", "Views", "Crawl_Date"])

# ==================== CÁC HÀM HỖ TRỢ ====================
def get_full_image_url(thumb_url):
    if not thumb_url or 'holder.png' in thumb_url:
        return ''
    return re.sub(r'-(\d+)(?=\.[a-zA-Z]+$)', '', thumb_url)

def get_article_data(url):
    """Lấy ảnh + lượt xem từ trang chi tiết bài viết"""
    headers = headers_base.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)
    
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Lấy ảnh (ưu tiên og:image)
        image_url = None
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            img = og['content'].strip()
            if 'holder.png' not in img and re.search(r'\.(jpg|jpeg|png|webp)', img.lower()):
                image_url = urljoin(url, img)

        # Lấy lượt views
        views = "0"
        views_li = soup.find('li', class_=re.compile(r'views', re.I))
        if views_li:
            text = views_li.get_text(strip=True)
            match = re.search(r'[\d.,]+', text.replace('.', '').replace(',', ''))
            if match:
                views = match.group(0)

        time.sleep(random.uniform(1.5, 3.0))
        return image_url, views

    except Exception as e:
        print(f"[ERROR] Lấy dữ liệu bài viết thất bại: {url} - {e}")
        return None, "0"


def scrape_page(page_num):
    global stop_scraping
    if stop_scraping:
        return []

    url = base_url if page_num == 1 else f"{base_url}?p={page_num}"
    headers = headers_base.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)

    try:
        resp = requests.get(url, headers=headers, timeout=25)
        if resp.status_code != 200:
            return []

        time.sleep(random.uniform(0.8, 2.2))
        soup = BeautifulSoup(resp.text, 'html.parser')
        items = []
        duplicate_count = 0

        for li in soup.find_all('li', class_='listitem clearfix'):
            if stop_scraping:
                break

            title_a = li.find('a', class_='title')
            if not title_a:
                continue
            title = title_a.find('h3').get_text(strip=True) if title_a.find('h3') else title_a.get_text(strip=True)
            link = urljoin(base_url, title_a.get('href', ''))

            if link in existing_links:
                duplicate_count += 1
                if duplicate_count >= 5:
                    stop_scraping = True
                    print(f"!!! >=5 bài trùng tại trang {page_num} → DỪNG!")
                continue

            desc = li.find('div', class_='desc')
            desc_text = desc.get_text(strip=True) if desc else ''

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
                'thumb': thumb,
                'date': datetime.now().strftime("%Y-%m-%d %H:%M")
            })

        if len(items) == 0 and page_num > 1:
            stop_scraping = True

        print(f"Trang {page_num}: {len(items)} bài mới | {duplicate_count} trùng")
        return items

    except Exception as e:
        print(f"Lỗi trang {page_num}: {e}")
        return []


# ==================== ĐỌC RSS CŨ & EXISTING LINKS ====================
existing_links = set()
old_items = []
if os.path.exists(output_file):
    try:
        tree = ET.parse(output_file)
        for item in tree.findall('.//item'):
            link = item.find('link').text.strip() if item.find('link') is not None else ''
            if link:
                existing_links.add(link)
                old_items.append({
                    'title': item.find('title').text or '',
                    'link': link,
                    'description': item.find('description').text or '',
                    'guid': link
                })
    except:
        pass

# ==================== CRAWL ====================
print("=== BẮT ĐẦU CRAWL KHOAHOC.TV ===")
stop_scraping = False
all_new_items = []
lock = threading.Lock()

# Trang 1
page1_items = scrape_page(1)
with lock:
    all_new_items.extend(page1_items)

# Các trang còn lại
if not stop_scraping and max_pages > 1:
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {executor.submit(scrape_page, p): p for p in range(2, max_pages + 1)}
        for future in as_completed(futures):
            if stop_scraping:
                break
            items = future.result()
            if items:
                with lock:
                    all_new_items.extend(items)

# ==================== GHI GOOGLE SHEET & LẤY ẢNH + VIEWS ====================
print("\n=== ĐANG GHI VÀO GOOGLE SHEET + LẤY ẢNH & VIEWS ===")
today = datetime.now().strftime("%Y-%m-%d %H:%M")

for item in all_new_items:
    # Ghi bài mới vào sheet
    image_url, views = get_article_data(item['link'])
    
    sheet.append_row([
        item['title'],
        item['date'],
        item['link'],
        image_url or "",
        views,
        today
    ])
    print(f"Đã thêm bài mới: {item['title'][:70]}... | Views: {views}")

# Cập nhật ảnh cho các bài cũ chưa có ảnh (tối đa 30 bài/lần để tránh timeout)
print("\n=== CẬP NHẬT ẢNH CHO BÀI CŨ CHƯA CÓ ===")
rows = sheet.get_all_values()
updated = 0
for row_idx, row in enumerate(rows[1:], start=2):
    if updated >= 30:          # Giới hạn mỗi lần chạy
        break
    if len(row) < 4 or not row[2].startswith('http'):
        continue
    if len(row) > 3 and row[3].strip().startswith('http'):
        continue  # đã có ảnh

    link = row[2].strip()
    image_url, views = get_article_data(link)
    
    if image_url or views != "0":
        sheet.update(f'D{row_idx}:E{row_idx}', [[image_url or "", views]])
        print(f"Cập nhật bài cũ dòng {row_idx}: Ảnh={'Có' if image_url else 'Không'} | Views={views}")
        updated += 1

# ==================== TẠO RSS ====================
print("\n=== TẠO FILE RSS ===")
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "KhoaHoc.tv - Tin tức khoa học mới nhất"
ET.SubElement(channel, "link").text = base_url
ET.SubElement(channel, "description").text = "Cập nhật tin tức khoa học, công nghệ từ KhoaHoc.tv"

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

for old in old_items:
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = old['title']
    ET.SubElement(item, "link").text = old['link']
    ET.SubElement(item, "guid", isPermaLink="true").text = old['guid']
    clean_desc = unescape(old['description'] or '')
    if not clean_desc.startswith('<![CDATA['):
        clean_desc = f"<![CDATA[{clean_desc}]]>"
    ET.SubElement(item, "description").text = clean_desc

xmlstr = ET.tostring(rss, encoding='unicode')
pretty_xml = minidom.parseString(xmlstr).toprettyxml(indent=" ")
clean_xml = "\n".join(line for line in pretty_xml.splitlines() if line.strip())

os.makedirs(output_dir, exist_ok=True)
with open(output_file, "w", encoding="utf-8") as f:
    f.write(clean_xml)

print(f"\nHOÀN THÀNH!")
print(f"- RSS: {output_file}")
print(f"- Google Sheet: {SHEET_NAME}")
print(f"- Thêm mới: {len(all_new_items)} bài")
