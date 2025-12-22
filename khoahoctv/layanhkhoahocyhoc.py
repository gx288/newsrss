import time
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import os

# === CẤU HÌNH ===
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'
SPREADSHEET_ID = '14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo'
SHEET_NAME = 'Khoahocyhoc'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
# =================

# Tạo credentials từ Secret (GitHub Actions)
if os.getenv('GOOGLE_SHEETS_CREDENTIALS'):
    os.makedirs('khoahoctv', exist_ok=True)
    with open(SERVICE_ACCOUNT_FILE, 'w', encoding='utf-8') as f:
        f.write(os.getenv('GOOGLE_SHEETS_CREDENTIALS'))

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

def get_first_article_image(url):
    print(f"[DEBUG] Đang truy cập bằng requests: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Ưu tiên 1: Lấy từ meta og:image (luôn là ảnh đại diện chính xác)
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            img_url = og_image['content'].strip()
            if 'holder.png' not in img_url and re.search(r'\.(jpg|jpeg|png|webp)', img_url.lower()):
                full_url = urljoin(url, img_url)
                print(f"[SUCCESS] Lấy ảnh từ og:image: {full_url}")
                return full_url
        
        # Ưu tiên 2: Nếu không có og:image (hiếm), lấy ảnh đầu tiên trong content (tránh holder)
        content = soup.find('div', class_=re.compile(r'entry-content|article-body|post-content', re.I)) or soup.body
        if content:
            for img in content.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''
                if src and 'holder.png' not in src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                    if any(ad in src.lower() for ad in ['ad', 'banner', 'logo', 'facebook']):
                        continue
                    full_url = urljoin(url, src)
                    print(f"[DEBUG] Lấy ảnh đầu tiên trong bài: {full_url}")
                    return full_url
        
        print("[DEBUG] Không tìm thấy ảnh phù hợp")
        return None
    
    except Exception as e:
        print(f"[ERROR] Requests lỗi: {e}")
        return None

# === XỬ LÝ SHEET ===
rows = sheet.get_all_values()
for row_idx, row in enumerate(rows[1:], start=2):
    if len(row) < 3:
        continue
    link = row[2].strip()  # Cột C
    current_image = row[3].strip() if len(row) > 3 else ''

    if not link:
        continue
    if current_image:
        print(f"[DEBUG] Dòng {row_idx}: Đã có ảnh → Bỏ qua")
        continue

    print(f"[INFO] Xử lý dòng {row_idx}: {link}")
    image_url = get_first_article_image(link)

    if image_url:
        sheet.update_cell(row_idx, 4, image_url)
        print(f"[SUCCESS] Đã ghi ảnh vào dòng {row_idx}: {image_url}")
    else:
        print(f"[FAIL] Không lấy được ảnh cho dòng {row_idx}")

    time.sleep(3)  # An toàn, tránh rate limit

print("=== HOÀN THÀNH TOÀN BỘ ===")
