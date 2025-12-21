import os
import random
import string
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Thư mục và file lưu
DIR = os.path.dirname(__file__)
FILE_PASS = os.path.join(DIR, 'passwords.txt')

print("=== BẮT ĐẦU CHẠY SCRIPT ===")

# Tạo file nếu chưa có
if not os.path.exists(FILE_PASS):
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        pass
    print(f"Tạo file passwords.txt mới tại: {FILE_PASS}")

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

try:
    print("\nBƯỚC 1: Truy cập trang đăng ký https://100like.vn/register")
    driver.get("https://100like.vn/register")
    time.sleep(5)

    print("Đang kiểm tra có đúng trang đăng ký không (tìm nút Đăng ký)...")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn.btn-primary"))
    )
    print("Vào trang đăng ký THÀNH CÔNG")

    print("Đang tạo username và password ngẫu nhiên...")
    username = ''.join(random.choices(string.digits, k=8)) + ''.join(random.choices(string.ascii_lowercase, k=5))
    password = ''.join(random.choices(string.digits, k=8))
    print(f"Username tạo: {username}")
    print(f"Password tạo: {password}")

    print("Đang nhập thông tin đăng ký...")
    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)

    print("Click nút Đăng ký...")
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary").click()

    print("Đang chờ chuyển sang trang /service (kiểm tra đăng ký thành công)...")
    WebDriverWait(driver, 20).until(EC.url_contains("/service"))
    print("ĐĂNG KÝ THÀNH CÔNG!")

    # Lưu tạm
    with open(FILE_PASS, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(f"{username} | {password} | Đăng ký OK | Trial pending...\n")
        f.write(content)
    print(f"Đã lưu tạm tài khoản vào passwords.txt")

    print("\nBƯỚC 2: Chuyển sang trang trial like https://100like.vn/fb/liketrial")
    driver.get("https://100like.vn/fb/liketrial")
    time.sleep(5)
    print("Vào trang trial thành công")

    print("Đang đọc dữ liệu từ Google Sheet (cột K, lấy dòng dưới cùng có nội dung)...")
    sheet_id = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid=0"
    
    try:
        df = pd.read_csv(csv_url)
        col_k = df.iloc[:, 10].dropna().astype(str).str.strip()
        col_k = col_k[col_k != '']
        if col_k.empty:
            raise Exception("Cột K không có dữ liệu nào")
        post_link = col_k.iloc[-1]
        print(f"Lấy thành công ID/Link từ cột K (dưới cùng): {post_link}")
    except Exception as sheet_error:
        raise Exception(f"Không đọc được Google Sheet - {str(sheet_error)}. "
                        "Nguyên nhân phổ biến: Sheet chưa public (Anyone with the link can view). "
                        "Hãy vào Sheet → Share → đổi thành Anyone with the link → Viewer.")

    print("Đang điền ID/Link vào ô input...")
    input_field = driver.find_element(By.CSS_SELECTOR, "input[placeholder='ID Hoặc Link Bài Viết']")
    input_field.clear()
    input_field.send_keys(post_link)
    print("Điền xong")

    print("Click nút Dùng Thử...")
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success").click()
    print("Đã click, đang chờ thông báo kết quả (6 giây)...")
    time.sleep(6)

    print("Đang tìm thông báo kết quả trên trang...")
    try:
        result_message = driver.find_element(By.CSS_SELECTOR, ".alert, .toast-message, .text-success, .text-danger, div[role='alert'], .notification").text
        print(f"Tìm thấy thông báo: {result_message}")
    except:
        print("Không tìm thấy alert rõ ràng, thử lấy text cuối trang...")
        result_message = driver.find_element(By.TAG_NAME, "body").text[-300:]
        print(f"Text cuối trang: {result_message}")

except Exception as e:
    result_message = f"LỖI: {str(e)}"
    print("\n=== CÓ LỖI XẢY RA ===")
    print(result_message)
    if 'username' in locals():
        with open(FILE_PASS, 'r+', encoding='utf-8') as f:
            content = f.read()
            f.seek(0)
            f.write(f"{username} | {password} | {result_message}\n")
            f.write(content)
        print("Đã lưu tài khoản + lỗi vào passwords.txt")

else:
    # Cập nhật kết quả cuối cùng
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if lines:
        parts = lines[0].split('|', 3)
        lines[0] = f"{parts[0].strip()} | {parts[1].strip()} | {parts[2].strip()} | {result_message}\n"
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"\nHOÀN THÀNH! Kết quả trial: {result_message}")

finally:
    driver.quit()
    print("\nĐóng browser. Script kết thúc.")

print("=== KẾT THÚC SCRIPT ===")
