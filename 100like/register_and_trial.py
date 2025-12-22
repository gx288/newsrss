import os
import random
import string
import time
import pandas as pd
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

# ==================== CẤU HÌNH DỄ SỬA ====================
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "Reels"
COLUMN_INDEX = 8              # Cột I
# ===============================================================================

DIR = os.path.dirname(__file__)
FILE_PASS = os.path.join(DIR, 'passwords.txt')

print("=== BẮT ĐẦU CHẠY SCRIPT ===")

if not os.path.exists(FILE_PASS):
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.write("# Username | Password | Link trial | Kết quả\n")
    print("Tạo file passwords.txt mới")

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
    # Bước 1: Đăng ký (giữ nguyên)
    print("\nBƯỚC 1: Đăng ký tài khoản mới")
    driver.get("https://100like.vn/register")
    time.sleep(5)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn.btn-primary"))
    )

    username = ''.join(random.choices(string.digits, k=8)) + ''.join(random.choices(string.ascii_lowercase, k=5))
    password = ''.join(random.choices(string.digits, k=8))
    print(f"Username: {username}")
    print(f"Password: {password}")

    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary").click()

    WebDriverWait(driver, 20).until(EC.url_contains("/service"))
    print("ĐĂNG KÝ THÀNH CÔNG!")

    with open(FILE_PASS, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(f"{username} | {password} | Chưa chọn link | Trial pending...\n")
        f.write(content)

    # Bước 2: Chọn link (giữ nguyên)
    print("\nBƯỚC 2: Chọn link từ Google Sheet")
    encoded_sheet = urllib.parse.quote_plus(SHEET_NAME)
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_sheet}"
    
    df = pd.read_csv(csv_url)
    print(f"Đọc sheet thành công - {len(df)} dòng")

    col_i = df.iloc[:, COLUMN_INDEX].dropna().astype(str).str.strip()
    col_i = col_i[col_i != '']
    if col_i.empty:
        raise Exception("Cột I không có dữ liệu")

    all_links = col_i.tolist()[::-1]
    print(f"Tổng {len(all_links)} link")

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

    print(f"Đã chạy thành công {len(used_links)} link trước đây")

    for link in all_links:
        if link not in used_links:
            selected_link = link
            print(f"Chọn link mới: {selected_link}")
            break

    if selected_link == "KHÔNG CÓ LINK MỚI":
        raise Exception("Hết link mới để chạy!")

    # Bước 3: Trial like - PHẦN ĐÃ SỬA CHÍNH
    print("\nBƯỚC 3: Thực hiện trial like")
    driver.get("https://100like.vn/fb/liketrial")
    time.sleep(5)

    input_field = driver.find_element(By.CSS_SELECTOR, "input[placeholder='ID Hoặc Link Bài Viết']")
    input_field.clear()
    input_field.send_keys(selected_link)
    print("Đã nhập link")

    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success").click()
    print("Đã click Dùng Thử")

    # Chờ toast hiện ra (khoảng 1-5 giây)
    time.sleep(5)

    # Ưu tiên bắt toast error (class chính xác bạn cung cấp)
    toast_selector = ".vue-notification-template.mmo-notification.error .notification-content"
    history_rows_selector = "div.col-md-8 table.table tbody tr"

    try:
        # Kiểm tra toast error trước
        error_toast = driver.find_element(By.CSS_SELECTOR, toast_selector).text.strip()
        if "dùng like thử miễn phí" in error_toast or "Bạn đã dùng" in error_toast:
            result_message = "LỖI: Bạn đã dùng like thử miễn phí"
        elif "Hết số lần dùng thử" in error_toast:
            result_message = "LỖI: Hết số lần dùng thử, quay lại ngày mai"
        else:
            result_message = f"LỖI TOAST: {error_toast}"
        print(f"Bắt được toast error: {result_message}")

    except:
        # Không có toast error → reload để cập nhật lịch sử và kiểm tra
        print("Không thấy toast error → reload page để kiểm tra lịch sử")
        driver.refresh()
        time.sleep(8)  # Chờ lịch sử load

        try:
            rows = driver.find_elements(By.CSS_SELECTOR, history_rows_selector)
            if rows:
                # Lấy ngày giờ của dòng đầu tiên (mới nhất)
                latest_time = rows[0].find_element(By.TAG_NAME, "td:last-child").text.strip()
                today = datetime.now().strftime("%d/%m/%Y")
                if today in latest_time or "22/12/2025" in latest_time:  # Linh hoạt với định dạng
                    result_message = "THÀNH CÔNG: Đã dùng thử thành công (có lịch sử mới)"
                    print(f"Lịch sử mới: {latest_time} → THÀNH CÔNG")
                else:
                    result_message = "KHÔNG RÕ: Có lịch sử nhưng không phải hôm nay"
            else:
                result_message = "KHÔNG RÕ: Không có lịch sử nào"
        except Exception as e:
            result_message = f"LỖI KIỂM TRA LỊCH SỬ: {str(e)}"

    print(f"Kết quả cuối cùng: {result_message}")

except Exception as e:
    result_message = f"LỖI CHUNG: {str(e)}"
    print(result_message)

finally:
    # Cập nhật file passwords.txt
    lines = []
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if lines:
        parts = lines[0].split('|', 3)
        lines[0] = f"{parts[0].strip()} | {parts[1].strip()} | {selected_link} | {result_message}\n"
    
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"Đã cập nhật passwords.txt: {lines[0].strip()}")

    driver.quit()
    print("\n=== SCRIPT KẾT THÚC ===")
