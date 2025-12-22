import time
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
import gspread
from google.oauth2.service_account import Credentials
import os

# === CẤU HÌNH ===
# File credentials.json sẽ được tạo tự động từ Secret trên GitHub Actions
# Nếu chạy local thì bạn đặt file credentials.json cùng thư mục khoahoctv/
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'

SPREADSHEET_ID = '14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo'
SHEET_NAME = 'Khoahocyhoc'

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
# =================

# Kiểm tra và tạo credentials từ biến môi trường nếu có (GitHub Actions)
if os.getenv('GOOGLE_SHEETS_CREDENTIALS'):
    # GitHub Actions: tạo file tạm từ secret
    os.makedirs('khoahoctv', exist_ok=True)
    with open(SERVICE_ACCOUNT_FILE, 'w', encoding='utf-8') as f:
        f.write(os.getenv('GOOGLE_SHEETS_CREDENTIALS'))

# Authenticate
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

def get_image_src(img_tag):
    """Hỗ trợ lazy-loading: src, data-src, data-lazy-src, srcset..."""
    src = (
        img_tag.get('src') or
        img_tag.get('data-src') or
        img_tag.get('data-lazy-src') or
        img_tag.get('data-original')
    )
    if not src:
        srcset = img_tag.get('srcset', '')
        match = re.search(r'https?://[^\s,]+', srcset)
        if match:
            src = match.group(0)
    return src

def is_ad_image(src):
    if not src:
        return True
    src_lower = src.lower()
    return any(k in src_lower for k in ['ad', 'banner', 'ads', 'sponsor', 'logo', 'facebook', 'share'])

def get_first_article_image(url, use_selenium=False):
    print(f"[DEBUG] Đang truy cập: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
    }

    if not use_selenium:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            print(f"[DEBUG] Requests lỗi: {e} → Chuyển sang Selenium")
            return get_first_article_image(url, use_selenium=True)
    else:
        try:
            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            driver = uc.Chrome(options=options)
            driver.get(url)
            time.sleep(6)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            driver.quit()
            print("[DEBUG] Selenium tải trang thành công")
        except Exception as e:
            print(f"[DEBUG] Selenium lỗi: {e}")
            return None

    # Ưu tiên 1: Ảnh featured / thumbnail
    featured = soup.find('div', class_=re.compile(r'featured|thumbnail|post-image|entry-thumb', re.I))
    if featured:
        img = featured.find('img')
        if img:
            src = get_image_src(img)
            if src and not is_ad_image(src):
                full = urljoin(url, src)
                print(f"[DEBUG] Ảnh featured: {full}")
                return full

    # Ưu tiên 2: Ảnh đầu tiên trong nội dung bài
    content = (
        soup.find('div', class_=re.compile(r'entry-content|article-body|content|post-content', re.I)) or
        soup.find('article') or
        soup.body
    )
    if content:
        for img in content.find_all('img'):
            src = get_image_src(img)
            if src and not is_ad_image(src):
                full = urljoin(url, src)
                print(f"[DEBUG] Ảnh đầu tiên trong bài: {full}")
                return full

    print("[DEBUG] Không tìm thấy ảnh phù hợp")
    return None

# === XỬ LÝ SHEET ===
rows = sheet.get_all_values()
for row_idx, row in enumerate(rows[1:], start=2):  # Bỏ header
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

    time.sleep(3)  # Tránh bị block

print("=== HOÀN THÀNH TOÀN BỘ ===")
