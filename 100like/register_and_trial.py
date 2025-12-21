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

# Thư mục lưu file
DIR = os.path.dirname(__file__)
FILE_PASS = os.path.join(DIR, 'passwords.txt')

# Tạo thư mục nếu chưa có (trong GitHub Actions thì đã có)
os.makedirs(DIR, exist_ok=True)

# Tạo file nếu chưa tồn tại
if not os.path.exists(FILE_PASS):
    open(FILE_PASS, 'w').close()

# Hàm tạo username: 8 số + 5 chữ cái thường bất kỳ, không dấu
def generate_username():
    numbers = ''.join(random.choices(string.digits, k=8))
    letters = ''.join(random.choices(string.ascii_lowercase, k=5))
    return numbers + letters

# Hàm tạo password: 8 số random
def generate_password():
    return ''.join(random.choices(string.digits, k=8))

# Setup Chrome headless cho GitHub Actions
options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--window-size=1920,1200')

driver = webdriver.Chrome(options=options)

try:
    # Bước 1: Truy cập trang đăng ký
    driver.get("https://100like.vn/register")
    time.sleep(3)

    # Kiểm tra có đúng trang đăng ký không (có nút Đăng ký)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button.btn.btn-primary"))
        )
        print("Đã vào đúng trang đăng ký 100like.vn")
    except:
        raise Exception("Không tìm thấy nút Đăng ký - Sai trang hoặc trang lỗi")

    # Tạo tài khoản
    username = generate_username()
    password = generate_password()

    # Nhập username và password
    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password)

    # Click Đăng ký
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary").click()

    # Chờ và kiểm tra chuyển sang trang service
    try:
        WebDriverWait(driver, 15).until(
            EC.url_contains("https://100like.vn/service")
        )
        print("Đăng ký thành công, đã chuyển sang trang service")
    except:
        raise Exception("Đăng ký thất bại - Không chuyển trang service")

    # Lưu tài khoản + password + kết quả tạm (sẽ cập nhật sau)
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.write(f"{username} | {password} | Đăng ký OK\n")
        f.writelines(lines)
    print(f"Đã lưu tài khoản: {username}")

    # Bước 2: Đi đến trang liketrial
    driver.get("https://100like.vn/fb/liketrial")
    time.sleep(3)

    # Đọc Google Sheet công khai (gid=0) - cột K (index 10)
    sheet_id = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid=0"
    df = pd.read_csv(csv_url)

    # Lấy các giá trị cột K không rỗng, ngược từ dưới lên (lấy cái đầu tiên có nội dung)
    col_k = df.iloc[:, 10].dropna().astype(str).str.strip()
    col_k = col_k[col_k != '']
    if col_k.empty:
        raise Exception("Cột K trong Google Sheet không có dữ liệu nào")

    post_id_or_link = col_k.iloc[-1]  # Lấy cái cuối cùng (dưới cùng)
    print(f"Lấy được ID/Link từ cột K (dưới lên): {post_id_or_link}")

    # Điền vào ô input
    input_field = driver.find_element(By.CSS_SELECTOR, "input[placeholder='ID Hoặc Link Bài Viết']")
    input_field.send_keys(post_id_or_link)

    # Click nút Dùng Thử
    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success").click()

    time.sleep(5)  # Chờ thông báo hiện

    # Lấy thông báo kết quả (thường là alert hoặc text gần nút)
    try:
        # Thử lấy text thông báo phổ biến (có thể điều chỉnh selector nếu cần)
        result = driver.find_element(By.CSS_SELECTOR, ".alert, .text-success, .text-danger, .notification").text
    except:
        result = "Không tìm thấy thông báo rõ ràng"

    print(f"Kết quả: {result}")

    # Cập nhật lại file với kết quả cuối cùng (dòng mới nhất lên đầu)
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    lines[0] = lines[0].strip() + f" | {result}\n"  # Cập nhật dòng đầu
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print("Hoàn thành toàn bộ quy trình!")

except Exception as e:
    print(f"LỖI: {e}")
    # Nếu có tài khoản đang tạo dở thì vẫn lưu với lỗi
    if 'username' in locals():
        with open(FILE_PASS, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(FILE_PASS, 'w', encoding='utf-8') as f:
            f.write(f"{username} | {password} | LỖI: {e}\n")
            f.writelines(lines)

finally:
    driver.quit()
