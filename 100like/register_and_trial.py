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

# Thư mục và file lưu tài khoản
DIR = os.path.dirname(__file__)
FILE_PASS = os.path.join(DIR, 'passwords.txt')

# Tạo file nếu chưa có
if not os.path.exists(FILE_PASS):
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        pass

def generate_username():
    numbers = ''.join(random.choices(string.digits, k=8))
    letters = ''.join(random.choices(string.ascii_lowercase, k=5))
    return numbers + letters

def generate_password():
    return ''.join(random.choices(string.digits, k=8))

# Setup Chrome headless (bắt buộc trên GitHub Actions)
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1200')

driver = webdriver.Chrome(options=options)

result_message = "Không rõ kết quả"

try:
    # Bước 1: Trang đăng ký
    driver.get("https://100like.vn/register")
    time.sleep(4)

    # Check đúng trang (có nút Đăng ký)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn.btn-primary"))
    )
    print("Vào trang đăng ký thành công")

    username = generate_username()
    password = generate_password()

    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary").click()

    # Check đăng ký OK
    WebDriverWait(driver, 15).until(EC.url_contains("/service"))
    print("Đăng ký thành công")

    # Lưu tạm
    with open(FILE_PASS, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(f"{username} | {password} | Đăng ký OK | Trial pending...\n")
        f.write(content)

    # Bước 2: Trang trial like
    driver.get("https://100like.vn/fb/liketrial")
    time.sleep(4)

    # Lấy link/ID từ cột K Google Sheet (dòng dưới cùng có dữ liệu)
    sheet_id = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid=0"
    df = pd.read_csv(csv_url)

    col_k = df.iloc[:, 10].dropna().astype(str).str.strip()
    col_k = col_k[col_k != '']
    if col_k.empty:
        raise Exception("Cột K Google Sheet không có dữ liệu")

    post_link = col_k.iloc[-1]
    print(f"Điền ID/Link: {post_link}")

    # Điền và bấm Dùng Thử
    input_field = driver.find_element(By.CSS_SELECTOR, "input[placeholder='ID Hoặc Link Bài Viết']")
    input_field.clear()
    input_field.send_keys(post_link)

    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success").click()
    time.sleep(6)

    # Lấy thông báo kết quả (thử nhiều selector phổ biến)
    try:
        result_message = driver.find_element(By.CSS_SELECTOR, ".alert, .toast-message, .text-success, .text-danger, div[role='alert']").text
    except:
        result_message = "Không thấy thông báo rõ ràng (có thể thành công nhưng không hiện text)"

    print(f"Kết quả trial: {result_message}")

except Exception as e:
    result_message = f"LỖI: {str(e)}"
    print(result_message)
    if 'username' in locals():
        with open(FILE_PASS, 'r+', encoding='utf-8') as f:
            content = f.read()
            f.seek(0)
            f.write(f"{username} | {password} | {result_message}\n")
            f.write(content)

else:
    # Cập nhật kết quả cuối cùng vào dòng mới nhất
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if lines:
        parts = lines[0].split('|', 3)
        lines[0] = f"{parts[0].strip()} | {parts[1].strip()} | {parts[2].strip()} | {result_message}\n"
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.writelines(lines)

finally:
    driver.quit()

print("Hoàn thành!")
