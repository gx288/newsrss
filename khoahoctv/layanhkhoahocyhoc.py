import time
import re
from urllib.parse import urljoin
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
import gspread
from google.oauth2.service_account import Credentials
import os

# === CẤU HÌNH ===
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'
SPREADSHEET_ID = '14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo'
SHEET_NAME = 'Khoahocyhoc'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
# =================

# Tạo credentials từ Secret (GitHub Actions) hoặc file local
if os.getenv('GOOGLE_SHEETS_CREDENTIALS'):
    os.makedirs('khoahoctv', exist_ok=True)
    with open(SERVICE_ACCOUNT_FILE, 'w', encoding='utf-8') as f:
        f.write(os.getenv('GOOGLE_SHEETS_CREDENTIALS'))

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

def get_first_article_image(url):
    print(f"[DEBUG] Đang mở trang bằng Selenium: {url}")
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-images")  # Tắt tải ảnh để nhanh hơn (nhưng vẫn load src từ JS)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    
    driver = uc.Chrome(options=options)
    
    try:
        driver.get(url)
        
        # Chờ nội dung bài viết load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.entry-content, div.article-body, div.post-content, article"))
        )
        
        # Scroll nhẹ để kích hoạt lazy-load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        time.sleep(3)  # Đợi JS thay src
        
        # Lấy tất cả img trong nội dung bài
        imgs = driver.find_elements(By.CSS_SELECTOR, 
            "div.entry-content img, div.article-body img, div.post-content img, article img")
        
        print(f"[DEBUG] Tìm thấy {len(imgs)} thẻ img trong bài viết")
        
        for i, img in enumerate(imgs):
            src = img.get_attribute('src') or ''
            data_src = img.get_attribute('data-src') or ''
            alt = img.get_attribute('alt') or ''
            
            print(f"[DEBUG] Img {i+1}: src='{src}' | data-src='{data_src}' | alt='{alt}'")
            
            # Bỏ qua holder.png và các ảnh không hợp lệ
            if 'holder.png' in src or not src:
                continue
            if any(k in src.lower() for k in ['ad', 'banner', 'ads', 'logo', 'facebook', 'share', 'sponsor']):
                print(f"[DEBUG] Bỏ qua ảnh quảng cáo: {src}")
                continue
            if not re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                continue
            
            full_url = urljoin(url, src)
            print(f"[SUCCESS] Lấy được ảnh đầu tiên hợp lệ: {full_url}")
            return full_url
        
        # Nếu không có trong body, thử featured image
        featured_img = driver.find_elements(By.CSS_SELECTOR, "div.featured-image img, div.post-thumbnail img, .entry-thumb img")
        if featured_img:
            src = featured_img[0].get_attribute('src')
            if src and 'holder.png' not in src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                full_url = urljoin(url, src)
                print(f"[SUCCESS] Lấy ảnh featured: {full_url}")
                return full_url
        
        print("[DEBUG] Không tìm thấy ảnh hợp lệ nào")
        return None
        
    except Exception as e:
        print(f"[ERROR] Selenium lỗi: {e}")
        return None
    finally:
        driver.quit()

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

    time.sleep(5)  # Tăng delay để tránh bị block

print("=== HOÀN THÀNH TOÀN BỘ ===")
