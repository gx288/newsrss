import os
import random
import string
import time
import pandas as pd
import urllib.parse  # Để encode tên sheet
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==================== CẤU HÌNH DỄ SỬA - CHỈ SỬA Ở ĐÂY KHI CẦN ====================
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "Reels"          # Tên sheet chính xác
COLUMN_INDEX = 8              # Cột I (A=0, B=1, ..., I=8)
# ===============================================================================

# Thư mục và file lưu
DIR = os.path.dirname(__file__)
FILE_PASS = os.path.join(DIR, 'passwords.txt')

print("=== BẮT ĐẦU CHẠY SCRIPT ===")
print(f"Config: Sheet ID = {SHEET_ID}")
print(f"        Sheet name = '{SHEET_NAME}'")
print(f"        Cột lấy link = I (index {COLUMN_INDEX})")

# Tạo file nếu chưa có
if not os.path.exists(FILE_PASS):
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.write("# Username | Password | Link trial | Kết quả\n")
    print(f"Tạo file passwords.txt mới")

print("Setup Chrome headless...")
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1200')

driver = webdriver.Chrome(options=options)
print("Khởi động Chrome thành công")

result_message = "Không rõ kết quả"
selected_link = "KHÔNG CÓ LINK MỚI"

try:
    # Bước 1: Đăng ký
    print("\nBƯỚC 1: Truy cập trang đăng ký")
    driver.get("https://100like.vn/register")
    time.sleep(5)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn.btn-primary"))
    )
    print("Vào trang đăng ký THÀNH CÔNG")

    username = ''.join(random.choices(string.digits, k=8)) + ''.join(random.choices(string.ascii_lowercase, k=5))
    password = ''.join(random.choices(string.digits, k=8))
    print(f"Username: {username}")
    print(f"Password: {password}")

    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary").click()

    WebDriverWait(driver, 20).until(EC.url_contains("/service"))
    print("ĐĂNG KÝ THÀNH CÔNG!")

    # Lưu tạm (chưa có link và kết quả)
    with open(FILE_PASS, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(f"{username} | {password} | Chưa chọn link | Trial pending...\n")
        f.write(content)
    print("Đã lưu tạm tài khoản")

    # Bước 2: Chọn link từ Google Sheet
    print("\nBƯỚC 2: Đọc Google Sheet để chọn link chưa chạy")
    encoded_sheet = urllib.parse.quote_plus(SHEET_NAME)
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_sheet}"
    
    try:
        df = pd.read_csv(csv_url)
        print(f"Đọc sheet '{SHEET_NAME}' thành công - {len(df)} dòng, {len(df.columns)} cột")
        
        col_i = df.iloc[:, COLUMN_INDEX].dropna().astype(str).str.strip()
        col_i = col_i[col_i != '']
        if col_i.empty:
            raise Exception("Cột I trong sheet 'Reels' không có dữ liệu")
        
        all_links = col_i.tolist()[::-1]  # Đảo ngược: từ dưới lên
        print(f"Tổng cộng {len(all_links)} link trong cột I")
        
    except Exception as e:
        raise Exception(f"Lỗi đọc Sheet: {str(e)}. Kiểm tra sheet public + tên sheet đúng.")

    # Đọc các link đã chạy thành công từ passwords.txt
    used_links = set()
    if os.path.getsize(FILE_PASS) > 0:
        with open(FILE_PASS, 'r', encoding='utf-8') as f:
            for line in f:
                if '|' in line and ("THÀNH CÔNG" in line or "thành công" in line or "Success" in line):
                    parts = line.split('|')
                    if len(parts) >= 3:
                        link = parts[2].strip()
                        if link.startswith("http"):
                            used_links.add(link)
    print(f"Đã có {len(used_links)} link chạy thành công trước đây")

    # Tìm link chưa chạy (từ dưới lên)
    for link in all_links:
        if link not in used_links:
            selected_link = link
            print(f"Chọn link CHƯA chạy: {selected_link}")
            break
    
    if selected_link == "KHÔNG CÓ LINK MỚI":
        raise Exception("Tất cả link trong cột I đã được chạy thành công rồi!")

    # Bước 3: Trial like
    print("\nBƯỚC 3: Thực hiện trial like")
    driver.get("https://100like.vn/fb/liketrial")
    time.sleep(5)
    print("Vào trang trial thành công")

    input_field = driver.find_element(By.CSS_SELECTOR, "input[placeholder='ID Hoặc Link Bài Viết']")
    input_field.clear()
    input_field.send_keys(selected_link)
    print("Đã điền link")

    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success").click()
    print("Click Dùng Thử, chờ kết quả...")
    time.sleep(8)

    try:
        result_message = driver.find_element(By.CSS_SELECTOR, ".alert, .toast-message, .text-success, .text-danger, div[role='alert'], .notification").text
    except:
        result_message = driver.find_element(By.TAG_NAME, "body").text[-400:]
    print(f"Kết quả trial: {result_message}")

except Exception as e:
    result_message = f"LỖI: {str(e)}"
    print("\n=== LỖI XẢY RA ===")
    print(result_message)

else:
    print("\nHOÀN THÀNH THÀNH CÔNG!")

finally:
    # Cập nhật file passwords.txt với link và kết quả cuối cùng
    lines = []
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if lines:
        parts = lines[0].split('|', 3)
        lines[0] = f"{parts[0].strip()} | {parts[1].strip()} | {selected_link} | {result_message}\n"
    
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"Đã cập nhật passwords.txt - Dòng mới nhất: {lines[0].strip()}")
    
    driver.quit()
    print("\nĐóng browser. Script kết thúc.")

print("=== KẾT THÚC SCRIPT ===")
