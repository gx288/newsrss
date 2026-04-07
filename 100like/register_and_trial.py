import os
import random
import string
import time
import pandas as pd
import urllib.parse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==================== CẤU HÌNH ====================
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "Khoahocyhoc"
COLUMN_INDEX = 12        # Cột chứa link (cột 12)
REFERRER_CODE = "432322"

DIR = os.path.dirname(__file__)
FILE_PASS = os.path.join(DIR, 'passwords.txt')
FILE_USED_LINKS = os.path.join(DIR, 'used_links.txt')

print("=== BẮT ĐẦU CHẠY SCRIPT ===")

# Tạo file nếu chưa tồn tại
if not os.path.exists(FILE_PASS):
    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.write("# Username | Password | Link trial | Kết quả | Thời gian\n")
    print("Tạo file passwords.txt mới")

if not os.path.exists(FILE_USED_LINKS):
    with open(FILE_USED_LINKS, 'w', encoding='utf-8') as f:
        pass
    print("Tạo file used_links.txt mới")

# ==================== SELENIUM SETUP ====================
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
    # Bước 1: Đăng ký tài khoản mới
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

    try:
        referrer_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "referrer"))
        )
        referrer_field.clear()
        referrer_field.send_keys(REFERRER_CODE)
        print(f"Đã nhập mã giảm giá: {REFERRER_CODE}")
    except Exception as e:
        print(f"Không tìm thấy hoặc không nhập được mã giảm giá: {str(e)}")

    driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary").click()
    WebDriverWait(driver, 20).until(EC.url_contains("/service"))
    print("ĐĂNG KÝ THÀNH CÔNG!")

    with open(FILE_PASS, 'r+', encoding='utf-8') as f:
        content = f.read()
        f.seek(0)
        f.write(f"{username} | {password} | Chưa chọn link | Trial pending... | {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(content)

    # Bước 2: Tìm link chưa chạy
    print("\nBƯỚC 2: Tìm link chưa chạy từ Google Sheet")

    used_links = set()
    if os.path.getsize(FILE_USED_LINKS) > 0:
        with open(FILE_USED_LINKS, 'r', encoding='utf-8') as f:
            used_links = {line.strip() for line in f if line.strip().startswith('http')}

    print(f"Đã chạy thành công {len(used_links)} link trước đây")

    encoded_sheet = urllib.parse.quote_plus(SHEET_NAME)
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_sheet}"
  
    df = pd.read_csv(csv_url)
    print(f"Đọc sheet thành công - {len(df)} dòng")

    col_i = df.iloc[:, COLUMN_INDEX].dropna().astype(str).str.strip()
    all_links = col_i[col_i.str.startswith('http')].tolist()[::-1]

    for link in all_links:
        if link not in used_links:
            selected_link = link
            print(f"✅ Chọn link mới: {selected_link}")
            break

    if selected_link == "KHÔNG CÓ LINK MỚI":
        raise Exception("Hết link mới để chạy!")

    # Bước 3: Thực hiện trial like
    print("\nBƯỚC 3: Thực hiện trial like")
    driver.get("https://100like.vn/fb/liketrial")
    time.sleep(6)

    input_field = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='ID Hoặc Link Bài Viết']"))
    )
    input_field.clear()
    input_field.send_keys(selected_link)
    print("Đã nhập link")

    submit_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success")
    submit_btn.click()
    print("Đã click Dùng Thử")

    # Chờ toast
    print("Chờ toast/notification hiện (tối đa 15s)...")
    time.sleep(3)
    toast_content_selector = ".vue-notification-template.mmo-notification .notification-content"
    toast_title_selector = ".vue-notification-template.mmo-notification .notification-title"
    success = False
    error_msg = None

    try:
        toast_content = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, toast_content_selector))
        )
        content_text = toast_content.text.strip()
        title_text = driver.find_element(By.CSS_SELECTOR, toast_title_selector).text.strip()
        print(f"Bắt được toast: Title='{title_text}' | Content='{content_text}'")

        if "error" in driver.find_element(By.CSS_SELECTOR, ".vue-notification-template.mmo-notification").get_attribute("class"):
            if "dùng like thử miễn phí" in content_text or "Bạn đã dùng" in content_text:
                error_msg = "LỖI: Bạn đã dùng like thử miễn phí"
            elif "Hết số lần dùng thử" in content_text:
                error_msg = "LỖI: Hết số lần dùng thử, quay lại ngày mai"
            else:
                error_msg = f"LỖI TOAST: {content_text}"
        else:
            success = True
            result_message = f"THÀNH CÔNG (toast): {content_text}"
    except:
        print("Không bắt được toast → chuyển sang check lịch sử")

    if not success and not error_msg:
        print("Reload page và chờ lịch sử load (tối đa 25s)...")
        driver.refresh()
        time.sleep(5)
        history_table_selector = "div.col-md-8.mb-5 table.table tbody"
        try:
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, history_table_selector + " tr"))
            )
            rows = driver.find_elements(By.CSS_SELECTOR, history_table_selector + " tr")
            if rows:
                latest_time_td = rows[0].find_elements(By.TAG_NAME, "td")[1]
                latest_time = latest_time_td.text.strip()
                print(f"Tìm thấy lịch sử mới nhất: {latest_time}")
                if datetime.now().strftime("%d/%m/%Y") in latest_time:
                    success = True
                    result_message = f"THÀNH CÔNG (lịch sử): {latest_time}"
                else:
                    result_message = f"KHÔNG RÕ: Có lịch sử nhưng không phải hôm nay ({latest_time})"
            else:
                result_message = "KHÔNG RÕ: Table có nhưng không có row nào"
        except Exception as e:
            result_message = f"LỖI CHECK LỊCH SỬ: {str(e)}"
            print(result_message)

    if success:
        result_message = result_message or "THÀNH CÔNG: Đã dùng thử thành công"
    elif error_msg:
        result_message = error_msg
    else:
        result_message = "KHÔNG RÕ: Không bắt được toast cũng không thấy lịch sử mới"

    print(f"Kết quả cuối cùng: {result_message}")

except Exception as e:
    result_message = f"LỖI CHUNG: {str(e)}"
    print(result_message)

finally:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Cập nhật passwords.txt
    lines = []
    with open(FILE_PASS, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if lines:
        parts = lines[0].split('|', 5)
        while len(parts) < 5:
            parts.append("")
        lines[0] = f"{parts[0].strip()} | {parts[1].strip()} | {selected_link} | {result_message} | {now}\n"

    with open(FILE_PASS, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    # Ghi vào used_links.txt nếu thành công
    if "THÀNH CÔNG" in result_message.upper():
        with open(FILE_USED_LINKS, 'a', encoding='utf-8') as f:
            f.write(selected_link + "\n")
        print(f"Đã thêm link vào used_links.txt: {selected_link}")

    print(f"Đã cập nhật passwords.txt với link: {selected_link}")
    driver.quit()
    print("\n=== SCRIPT KẾT THÚC ===")
